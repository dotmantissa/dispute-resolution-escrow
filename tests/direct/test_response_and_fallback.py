from datetime import datetime,timezone
import pytest


def warp(vm,stamp):vm.warp(datetime.fromtimestamp(stamp,timezone.utc).isoformat())


def test_payee_must_accept_recorded_policy_before_delivery(create,escrow,direct_vm,direct_bob,evidence):
    eid=create()
    direct_vm.sender=direct_bob
    d=evidence['delivery-full.md']
    with direct_vm.expect_revert('accept engagement'):
        escrow.claim_delivery(eid,d['url'],d['sha256'])
    escrow.accept_engagement(eid)
    r=escrow.get_escrow(eid)
    assert r['engagement_accepted'] and r['fallback_payee_bps']==5000
    with direct_vm.expect_revert('already accepted'):escrow.accept_engagement(eid)
    escrow.claim_delivery(eid,d['url'],d['sha256'])


@pytest.mark.parametrize('rate',[0,1,999,True])
def test_bonds_below_ten_percent_are_rejected(create,direct_vm,rate):
    with direct_vm.expect_revert('Bond rate'):create(bond_bps=rate,prepay=False)


def test_rebuttal_is_authenticated_and_bounded(disputed,escrow,direct_vm,direct_bob,direct_charlie,evidence):
    d=evidence['delivery-half.md']
    direct_vm.sender=direct_charlie
    with direct_vm.expect_revert('Only escrow parties'):
        escrow.submit_evidence(disputed,d['url'],d['sha256'])
    direct_vm.sender=direct_bob
    escrow.submit_evidence(disputed,d['url'],d['sha256'])
    r=escrow.get_escrow(disputed)
    assert r['supplements'][0]['role']=='payee_rebuttal'
    assert r['supplements'][0]['submitted_by'].lower()==direct_bob.as_hex.lower()
    assert r['supplements'][0]['text']
    with direct_vm.expect_revert('already submitted'):
        escrow.submit_evidence(disputed,d['url'],d['sha256'])
    for name in ['delivery-none.md','delivery-injection.md']:
        doc=evidence[name];escrow.submit_evidence(disputed,doc['url'],doc['sha256'])
    doc=evidence['dispute-none.md']
    with direct_vm.expect_revert('three supplements'):
        escrow.submit_evidence(disputed,doc['url'],doc['sha256'])


def test_adjudication_waits_for_response_or_both_parties(disputed,escrow,direct_vm,direct_alice,direct_bob,evidence):
    with direct_vm.expect_revert('Response window'):escrow.adjudicate(disputed)
    direct_vm.sender=direct_alice
    escrow.finish_evidence(disputed)
    with direct_vm.expect_revert('Response window'):escrow.adjudicate(disputed)
    d=evidence['dispute-half.md']
    with direct_vm.expect_revert('finished evidence'):
        escrow.submit_evidence(disputed,d['url'],d['sha256'])
    direct_vm.sender=direct_bob
    escrow.finish_evidence(disputed)
    assert escrow.get_escrow(disputed)['evidence_closed']
    with direct_vm.expect_revert('Evidence window closed'):
        escrow.submit_evidence(disputed,d['url'],d['sha256'])


def test_response_deadline_closes_rebuttal(disputed,escrow,direct_vm,direct_bob,evidence):
    r=escrow.get_escrow(disputed);warp(direct_vm,r['evidence_deadline'])
    direct_vm.sender=direct_bob;d=evidence['delivery-half.md']
    with direct_vm.expect_revert('Evidence window closed'):
        escrow.submit_evidence(disputed,d['url'],d['sha256'])


@pytest.mark.parametrize('share',[0,1,3333,5000,10000])
def test_agreed_fallback_prevents_indefinite_disputed_custody(create,escrow,fund,direct_vm,direct_alice,direct_bob,direct_charlie,evidence,share):
    eid=create(fallback_payee_bps=share,response_period=2,adjudication_period=3)
    direct_vm.sender=direct_bob;escrow.accept_engagement(eid)
    doc=evidence['delivery-full.md'];escrow.claim_delivery(eid,doc['url'],doc['sha256'])
    fund(1001);doc=evidence['dispute-good-faith.md']
    escrow.dispute(eid,doc['url'],doc['sha256'],1001)
    r=escrow.get_escrow(eid)
    warp(direct_vm,r['resolution_deadline']-1)
    with direct_vm.expect_revert('still open'):escrow.resolve_expired_dispute(eid)
    warp(direct_vm,r['resolution_deadline']);direct_vm.sender=direct_charlie
    with direct_vm.expect_revert('Resolution deadline'):escrow.adjudicate(eid)
    escrow.resolve_expired_dispute(eid)
    settled=escrow.get_escrow(eid)
    assert settled['payee_credit']==10001*share//10000
    assert settled['payer_credit']==11002-settled['payee_credit']
    assert not settled['payer_bad_faith']
    assert escrow.get_accounting()['locked_bonds']==0 and escrow.get_accounting()['conserved']
    with direct_vm.expect_revert('DISPUTED'):escrow.resolve_expired_dispute(eid)


def test_total_case_document_budget_is_enforced(disputed,escrow,direct_vm,direct_bob,evidence):
    r=escrow.get_escrow(disputed);r['document_bytes']=65536;escrow._save(r)
    direct_vm.sender=direct_bob;d=evidence['delivery-half.md']
    with direct_vm.expect_revert('65536 bytes'):escrow.submit_evidence(disputed,d['url'],d['sha256'])
    assert escrow.get_escrow(disputed)['supplements']==[]


def test_exact_consensus_compatibility_for_all_parseable_payouts(module):
    states=[{'conclusive':True,'payee_bps':s,'payer_bad_faith':False,'reason':'Evidence supports this allocation.'} for s in range(0,10001,100)]
    states += [states[-1]|{'payer_bad_faith':True},states[0]|{'conclusive':False}]
    def allocation(d,p,b):
        if not d['conclusive']:return ('LOCKED',p,b)
        earned=p*d['payee_bps']//10000
        return earned+(b if d['payer_bad_faith'] else 0),p-earned+(0 if d['payer_bad_faith'] else b)
    for leader in states:
        leader=module._parse_decision(leader)
        for validator in states:
            validator=module._parse_decision(validator)
            same=module._same_decision(leader,validator)
            assert same==all(leader[k]==validator[k] for k in ('conclusive','payee_bps','payer_bad_faith'))
            if same:
                for p in [1,10001,10**18,(1<<255)-1]:
                    assert allocation(leader,p,1001)==allocation(validator,p,1001)


def test_opponent_cannot_consume_reserved_evidence_capacity(create,escrow,direct_vm,direct_alice,direct_bob):
    eid=create()
    record=escrow.get_escrow(eid)
    # Budget checks operate on detached records before any persistent state update.
    payee={'submitted_by':record['payee'],'text':'x'*32768}
    escrow._document_budget(record,payee)
    assert record['payee_document_bytes']==32768
    payer={'submitted_by':record['payer'],'text':'x'*16384}
    escrow._document_budget(record,payer)
    assert record['payer_document_bytes']>=16384
    with direct_vm.expect_revert('Party evidence'):
        escrow._document_budget(record,{'submitted_by':record['payee'],'text':'y'})


def test_terms_cap_guarantees_space_for_initial_dispute(module):
    assert module.MAX_PARTY_BYTES-module.MAX_TERMS_BYTES>=16384
    assert 2*module.MAX_PARTY_BYTES==module.MAX_CASE_BYTES
