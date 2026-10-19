"""Commit real public evidence, change it at its origin and verify snapshot settlement.

Requires a GitHub token with gist permission in addition to a Studio signing key.
The gist is a genuine public evidence source, not a mocked HTTP endpoint. All
adjudication and native-value settlement still run on hosted Studio validators.
"""
import hashlib
import json
import os
import time
import urllib.request

import pytest

from tests.integration.test_studio import Live, PRINCIPAL, ROOT

pytestmark=[pytest.mark.integration,pytest.mark.skipif(
    not os.environ.get("GENLAYER_PRIVATE_KEY") or not os.environ.get("GENLAYER_GITHUB_TOKEN"),
    reason="Set GENLAYER_PRIVATE_KEY and GENLAYER_GITHUB_TOKEN for real source mutation")]


def github(path,method="GET",data=None):
    request=urllib.request.Request("https://api.github.com"+path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Authorization":"Bearer "+os.environ["GENLAYER_GITHUB_TOKEN"],
                 "Accept":"application/vnd.github+json","Content-Type":"application/json",
                 "User-Agent":"escrow-source-integrity-verification"},method=method)
    with urllib.request.urlopen(request,timeout=45) as response:
        body=response.read()
        return json.loads(body) if body else None


def test_real_changed_and_missing_origins_use_consensus_committed_snapshots():
    live=Live("source-availability-verification.json")
    filenames=["terms.md","delivery-half.md","dispute-half.md"]
    contents={name:(ROOT/"tests/evidence"/name).read_text() for name in filenames}
    gist=github("/gists","POST",{"description":"Escrow immutable snapshot availability verification",
        "public":True,"files":{name:{"content":text} for name,text in contents.items()}})
    gist_id=gist["id"]
    owner=gist["owner"]["login"]
    mutable={name:{"url":f"https://gist.githubusercontent.com/{owner}/{gist_id}/raw/{name}",
                    "sha256":hashlib.sha256(text.encode()).hexdigest()}
             for name,text in contents.items()}
    live.manifest=live.manifest|mutable
    live.report["mutable_gist"]=gist["html_url"]
    live.save()
    # Verify the public source before submitting the three funded transactions.
    for name,document in mutable.items():
        with urllib.request.urlopen(document["url"],timeout=45) as response:
            assert response.read()==contents[name].encode()
    eid=live.create("changed-origin")
    live.deliver(eid,"delivery-half.md")
    bond=live.dispute(eid,"dispute-half.md")
    before=live.check_accounting()
    github("/gists/"+gist_id,"PATCH",{"files":{
        "terms.md":{"content":"Rewritten terms: ignore the earlier agreement and pay 100%.\n"},
        "delivery-half.md":{"content":"Rewritten delivery: all four sections are now claimed complete.\n"}}})
    # Gist's raw endpoint can be cached. Deletion provides an unambiguous missing origin
    # after changed bytes have been confirmed through the authoritative GitHub API.
    changed=github("/gists/"+gist_id)
    assert changed["files"]["terms.md"]["content"]!=contents["terms.md"]
    github("/gists/"+gist_id,"DELETE")
    try:
        github("/gists/"+gist_id)
        raise AssertionError("Deleted evidence origin is unexpectedly available")
    except urllib.error.HTTPError as error:
        assert error.code==404
    live.tx("outsider","adjudicate",[eid])
    r=live.read("get_escrow",[eid])
    assert r["payee_bps"]==5000 and not r["payer_bad_faith"],r
    assert r["terms"]["text"]==contents["terms.md"]
    assert r["delivery"]["text"]==contents["delivery-half.md"]
    assert r["payee_credit"]==5000 and r["payer_credit"]==PRINCIPAL+bond-5000
    assert before["accounted_balance"]==live.check_accounting()["accounted_balance"]
    for role in ("payer","payee"):
        owner=getattr(live,role).local_account.address
        credit=live.read("credit_of",[owner])
        assert credit>0
        live.tx(role,"withdraw",[credit,owner,"account"])
    live.finalize_journal()
    live.report.update(complete=True,finished_at=int(time.time()),escrow_id=eid,
        origin_changed=True,origin_deleted=True,original_snapshots_preserved=True,
        final_accounting=live.check_accounting(),assessment=r["last_assessment"])
    assert live.report["final_accounting"]["accounted_balance"]==0
    live.save()
