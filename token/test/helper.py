from plenum.common.constants import TXN_TYPE
from plenum.common.types import f
from plenum.server.plugin.token.constants import MINT_PUBLIC, OUTPUTS, XFER_PUBLIC, \
    EXTRA, INPUTS, TOKEN_LEDGER_ID, GET_UTXO, ADDRESS
from plenum.test.helper import waitForSufficientRepliesForRequests


def public_mint_request(trustees, outputs):
    signatures = {}
    op = {
        TXN_TYPE: MINT_PUBLIC,
        OUTPUTS: outputs,
    }
    first_trustee = trustees[0]
    request = first_trustee.sign_using_multi_sig(
        op, identifier=first_trustee.defaultId)
    for wallet in trustees[1:]:
        signatures[wallet.defaultId] = wallet.do_multi_sig_on_req(
            request, identifier=wallet.defaultId)
    return request


def send_public_mint(looper, trustees, outputs, sender_client):
    request = public_mint_request(trustees, outputs)
    sender_client.submitReqs(request)
    waitForSufficientRepliesForRequests(looper, sender_client,
                                        requests=[request])
    return request


def do_public_minting(looper, trustees, sender_client, total_mint,
                      sf_master_share, sf_address, seller_address):
    seller_share = total_mint - sf_master_share
    outputs = [[sf_address, sf_master_share], [seller_address, seller_share]]
    request = send_public_mint(looper, trustees, outputs, sender_client)
    result, _ = sender_client.getReply(request.identifier, request.reqId)
    return result


def xfer_request(inputs, outputs, extra_data=None):
    payload = {
        TXN_TYPE: XFER_PUBLIC,
        OUTPUTS: outputs,
        EXTRA: extra_data,
    }
    wallet, address, seq_no = inputs[0]
    request = wallet.sign_using_output(address, seq_no, op=payload)
    for wallet, address, seq_no in inputs[1:]:
        wallet.sign_using_output(address, seq_no, request=request)
    return request


def send_xfer(looper, inputs, outputs, sender_client, extra_data=None):
    request = xfer_request(inputs, outputs, extra_data)
    sender_client.submitReqs(request)
    waitForSufficientRepliesForRequests(looper, sender_client,
                                        requests=[request])
    return request


def check_output_val_on_all_nodes(nodes, address, amount):
    for node in nodes:
        handler = node.get_req_handler(ledger_id=TOKEN_LEDGER_ID)
        assert float(amount) in [out.value for out in
                                 handler.utxo_cache.get_unspent_outputs(
                                     address, is_committed=True)]


def get_utxo_request(address, sender_wallet, sender_client):
    op = {
        TXN_TYPE: GET_UTXO,
        ADDRESS: address,
    }
    request = sender_wallet.signOp(op)
    sender_client.submitReqs(request)
    return request


def send_get_utxo(looper, address, sender_wallet, sender_client):
    request = get_utxo_request(address, sender_wallet, sender_client)
    waitForSufficientRepliesForRequests(looper, sender_client,
                                        requests=[request])
    return request


def inputs_outputs(*input_token_wallets, output_addr, change_addr=None,
                   change_amount=None):
    inputs = []
    out_amount = 0
    for tw in input_token_wallets:
        addr, vals = next(iter(tw.get_all_utxos().items()))
        inputs.append([tw, addr.address, vals[0][0]])
        out_amount += vals[0][1]

    if change_amount is not None:
        assert change_amount <= out_amount
        out_amount -= change_amount

    outputs = [[output_addr, out_amount], ]
    if change_addr:
        outputs.append([change_addr, change_amount])
    return inputs, outputs
