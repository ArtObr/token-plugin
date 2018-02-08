from collections import OrderedDict
from operator import itemgetter
from typing import Dict, Optional, Tuple

import math

from ledger.util import F
from plenum.client.wallet import Wallet
from plenum.common.constants import TXN_TYPE
from plenum.common.did_method import DidMethods
from plenum.common.messages.fields import TxnSeqNoField
from plenum.common.request import Request
from plenum.common.signer_simple import SimpleSigner
from plenum.common.util import lxor
from plenum.server.plugin.token.constants import INPUTS, GET_UTXO, OUTPUTS, XFER_PUBLIC


class Address:
    def __init__(self, seed=None):
        self.signer = SimpleSigner(seed=seed)
        self.address = self.signer.verkey
        self.outputs = [{}, {}]  # Unspent and Spent

    def is_unspent(self, seq_no):
        return seq_no in self.outputs[0]

    def spent(self, seq_no):
        val = self.outputs[0].pop(seq_no, None)
        if val:
            self.outputs[1][seq_no] = val

    def add_utxo(self, seq_no, val):
        self.outputs[0][seq_no] = val

    @property
    def all_utxos(self):
        return [(seq_no, val) for seq_no, val in self.outputs[0].items()]

    @property
    def total_amount(self):
        return sum(v for v in self.outputs[0].values())


class TokenWallet(Wallet):
    txn_seq_no_valdator = TxnSeqNoField()

    def __init__(self,
                 name: str=None,
                 supportedDidMethods: DidMethods=None):
        super().__init__(name, supportedDidMethods)
        self.addresses = OrderedDict()  # type: OrderedDict[str, Address]
        self.reply_handlers = {
            GET_UTXO: self.handle_get_utxo_response,
            XFER_PUBLIC: self.handle_xfer
        }

    def add_new_address(self, address: Address=None, seed=None):
        assert address or seed
        if not address:
            address = Address(seed=seed)
        assert address.address not in self.addresses
        self.addresses[address.address] = address

    def sign_using_output(self, id, seq_no, op: Dict=None,
                          request: Request=None):
        assert lxor(op, request)
        # assert self.addresses[id].is_unspent(seq_no)
        if op:
            request = Request(reqId=Request.gen_req_id(), operation=op)
        existing_inputs = request.operation.get(INPUTS, [])
        request.operation[INPUTS] = [[id, seq_no], ]
        signature = self.addresses[id].signer.sign(request.signingState(id))
        request.add_signature(id, signature)
        request.operation[INPUTS] = existing_inputs + [[id, seq_no], ]
        return request

    def get_all_utxos(self, address=None):
        if address is not None:
            assert address in self.addresses
            return {self.addresses[address]: self.addresses[address].all_utxos}
        else:
            return {address: address.all_utxos
                    for address in self.addresses.values()}

    def get_total_amount(self, address=None):
        if address is not None:
            assert address in self.addresses
            return self.addresses[address].total_amount
        else:
            return sum(addr.total_amount for addr in self.addresses.values())

    def on_reply_from_network(self, observer_name, req_id, frm, result,
                              num_replies):
        typ = result.get(TXN_TYPE)
        if typ and typ in self.reply_handlers:
            self.reply_handlers[typ](result)

    def handle_get_utxo_response(self, response):
        self._update_outputs(response[OUTPUTS])

    def handle_xfer(self, response):
        self._update_inputs(response[INPUTS])
        self._update_outputs(response[OUTPUTS], response[F.seqNo.name])

    def _update_inputs(self, inputs):
        for addr, seq_no in inputs:
            if addr in self.addresses:
                self.addresses[addr].spent(seq_no)

    def _update_outputs(self, outputs, txn_seq_no=None):
        for output in outputs:
            if len(output) == 2:
                error = self.txn_seq_no_valdator.validate(txn_seq_no)
                if error:
                    raise ValueError(error)
                addr, val = output
                seq_no = txn_seq_no
            elif len(output) == 3:
                addr, seq_no, val = output
            else:
                raise ValueError('Cannot handle output {}'.format(output))
            if addr in self.addresses:
                assert seq_no not in self.addresses[addr].outputs[0]
                self.addresses[addr].add_utxo(seq_no, val)

    def get_min_utxo_ge(self, amount, address=None) -> Optional[Tuple]:
        # Get minimum utxo greater than or equal to `amount`
        all_utxos = self.get_all_utxos(address=address)
        minimum = None

        def _greater_than(tpl):
            return tpl[1] if tpl[1] >= amount else math.inf

        if all_utxos:
            for addr, lst in all_utxos.items():
                if not lst:
                    continue
                min_val = min(lst, key=_greater_than)
                minimum = (addr.address, *min_val) if (
                    minimum is None or min_val[-1] < minimum[-1]) else minimum
        return minimum

    def get_val(self, address, seq_no):
        # Get value of unspent output (address and seq_no), can raise KeyError
        return self.addresses[address].outputs[0][seq_no]
