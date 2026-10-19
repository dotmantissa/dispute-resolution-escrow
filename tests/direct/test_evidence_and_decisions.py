import hashlib
import json

import pytest


@pytest.mark.parametrize("url",[
    "http://example.com/doc","https://localhost/doc","https://127.0.0.1/doc",
    "https://[::1]/doc","https://example.com:443/doc","https://u:p@example.com/doc",
    "https://example.com/doc#change","https://host.local/doc","https://host.internal/doc",
    "https://example.com/with space","https://host.test/doc","https://host.invalid/doc",
])
def test_restricted_urls(module,direct_vm,url):
    with direct_vm.expect_revert():
        module._url(url)


@pytest.mark.parametrize("url",["https://example.com","https://raw.githubusercontent.com/a/b?revision=1","https://evidence.example.org/path"])
def test_public_https_urls(module,url):
    module._url(url)


@pytest.mark.parametrize("digest",["a"*63,"A"*64,"0x"+"a"*64,"z"*64,""])
def test_digest_format(module,direct_vm,digest):
    with direct_vm.expect_revert("lowercase SHA-256"):
        module._digest(digest)


@pytest.mark.parametrize("body,error",[(b"","size"),(b"x"*32769,"size"),(b"\xff","UTF-8"),(b"\x00","binary"),(b" \n","Empty")])
def test_raw_document_validation(module,direct_vm,body,error):
    with direct_vm.expect_revert(error):
        module._document_bytes(body,hashlib.sha256(body).hexdigest())


def test_document_hash_mismatch_and_size_boundary(module,direct_vm):
    with direct_vm.expect_revert("mismatch"):
        module._document_bytes(b"a","0"*64)
    body=b"x"*32768
    assert module._document_bytes(body,hashlib.sha256(body).hexdigest())==body.decode()


def test_hash_mismatch_does_not_create_escrow(escrow,direct_vm,direct_bob,evidence):
    direct_vm.value=10
    before=escrow.get_accounting()
    with direct_vm.expect_revert("mismatch"):
        escrow._create_escrow("mismatch",direct_bob.as_hex,evidence["terms.md"]["url"],"0"*64,100,100,1000)
    assert escrow.get_accounting()==before


BASE={"conclusive":True,"payee_bps":5000,"payer_bad_faith":False,"reason":"Two of four equal sections delivered."}


@pytest.mark.parametrize("changes",[
    {"conclusive":"true"},{"conclusive":1},{"payee_bps":True},{"payee_bps":"5000"},
    {"payee_bps":50.5},{"payee_bps":5050},{"payee_bps":-100},{"payee_bps":10100},
    {"payer_bad_faith":"false"},{"payer_bad_faith":True},{"reason":""},{"reason":"x"*2001},
    {"conclusive":False},{"conclusive":False,"payee_bps":0,"payer_bad_faith":True},
])
def test_invalid_model_outputs_are_rejected(module,direct_vm,changes):
    with direct_vm.expect_revert("LLM_ERROR"):
        module._parse_decision(BASE|changes)


@pytest.mark.parametrize("raw",["garbage","[]","null",{},[]])
def test_missing_or_malformed_model_outputs(module,direct_vm,raw):
    with direct_vm.expect_revert("LLM_ERROR"):
        module._parse_decision(raw)


@pytest.mark.parametrize("raw",[BASE,json.dumps(BASE),"```json\n"+json.dumps(BASE)+"\n```"])
def test_json_and_fenced_json_parse_identically(module,raw):
    assert module._parse_decision(raw)==BASE


def test_inconclusive_and_full_bad_faith_are_distinct_valid_results(module):
    assert module._parse_decision(BASE|{"conclusive":False,"payee_bps":0})["conclusive"] is False
    assert module._parse_decision(BASE|{"payee_bps":10000,"payer_bad_faith":True})["payer_bad_faith"] is True


@pytest.mark.parametrize("changes",[{"payee_bps":4900},{"payer_bad_faith":True},{"conclusive":False}])
def test_independent_consensus_disagrees_on_any_economic_difference(module,changes):
    assert not module._same_decision(BASE,BASE|changes)


def test_consensus_ignores_wording_but_requires_identical_economics(module):
    assert module._same_decision(BASE,BASE|{"reason":"Equivalent explanation with different phrasing."})
