"""Account-specific exit checks for the retired Studio qualification fixture.

This is incident cleanup, not an administrator API in the production contract.
Native delivery and both actual account signatures are verified separately on Studio.
"""
from pathlib import Path
import ast
from gltest.direct.vm import VMContext
from gltest.direct.loader import load_contract_class, _allocate_contract, _make_contract_proxy

def test_retired_qualification_exit_requires_exact_bilateral_consent():
    path = Path(__file__).parents[1] / 'integration/contracts/qualification_custody_exit.py'
    tree = ast.parse(path.read_text())
    constants = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and (node.targets[0].id in ('_TEST_CUSTODY_EXIT', '_TEST_EXIT_SHA256'))}
    plan = constants['_TEST_CUSTODY_EXIT']
    digest = constants['_TEST_EXIT_SHA256']

    class TestAddress(bytes):

        @property
        def as_hex(self):
            return '0x' + self.hex()
    address = TestAddress.fromhex(plan['address'][2:])
    payer, payee = [TestAddress.fromhex(a[2:]) for a in plan['allocations']]
    outsider = TestAddress(b'\x19' * 20)
    vm = VMContext()
    vm._contract_address = address
    vm.sender = payer
    checks = []
    with vm.activate():
        cls = load_contract_class(path, vm)
        instance = _allocate_contract(cls, vm, payer.as_hex)
        api = _make_contract_proxy(instance)
        import sys
        module = sys.modules[cls.__module__]
        gl_module = sys.modules['genlayer.gl']
        gl_module.message = gl_module.message._replace(contract_address=module.Address(plan['address']))
        vm._storage.restore({})
        vm.deal(address, plan['native_balance'])
        state = api.get_test_recovery()
        assert state['native_balance'] == 300033 and (not state['emitted']) and (not any(state['approvals'].values()))
        checks.append('empty accepted storage')
        vm.sender = outsider
        with vm.expect_revert('Only the two original'):
            api.authorize_test_recovery(digest)
        checks.append('unrelated signer rejected')
        vm.sender = payer
        with vm.expect_revert('digest mismatch'):
            api.authorize_test_recovery('0' * 64)
        checks.append('different payout plan rejected')
        with vm.expect_revert('Both original'):
            api.emit_test_recovery()
        api.authorize_test_recovery(digest)
        with vm.expect_revert('Both original'):
            api.emit_test_recovery()
        checks.append('one party cannot emit')
        vm.sender = payee
        api.authorize_test_recovery(digest)
        vm.deal(address, 300032)
        with vm.expect_revert('native balance differs'):
            api.emit_test_recovery()
        checks.append('uncommitted balance rejected')
        vm.deal(address, 300033)
        api.emit_test_recovery()
        assert api.get_test_recovery()['emitted']
        checks.append('both exact approvals permit emission')
        with vm.expect_revert('already emitted'):
            api.emit_test_recovery()
        checks.append('emission replay rejected')
    assert len(checks) == 7
