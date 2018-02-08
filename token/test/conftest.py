import pytest

from ledger.util import F
from plenum.client.wallet import Wallet
from plenum.common.constants import DOMAIN_LEDGER_ID
from plenum.common.signer_simple import SimpleSigner
from plenum.common.util import randomSeed
from plenum.server.plugin.token.client_authnr import TokenAuthNr
from plenum.server.plugin.token.constants import TOKEN_LEDGER_ID
from plenum.server.plugin.token.main import update_node_class, update_node_obj
from plenum.server.plugin.token.util import register_token_wallet_with_client
from plenum.server.plugin.token.wallet import TokenWallet
from plenum.test.plugin.helper import getPluginPath
from plenum.test.plugin.token.helper import send_get_utxo, send_xfer
from plenum.test.test_node import TestNode


def build_wallets_from_data(name_seeds):
    wallets = []
    for name, seed in name_seeds:
        w = Wallet(name)
        w.addIdentifier(seed=seed.encode())
        wallets.append(w)
    return wallets


@pytest.fixture(scope="module")
def SF_token_wallet():
    return TokenWallet('SF_MASTER')


@pytest.fixture(scope="module")
def SF_address(SF_token_wallet):
    seed = 'sf000000000000000000000000000000'.encode()
    SF_token_wallet.add_new_address(seed=seed)
    return next(iter(SF_token_wallet.addresses.keys()))


@pytest.fixture(scope="module")
def seller_token_wallet():
    return TokenWallet('SELLER')


@pytest.fixture(scope="module")
def seller_address(seller_token_wallet):
    # Token selling/buying platform's address
    seed = 'se000000000000000000000000000000'.encode()
    seller_token_wallet.add_new_address(seed=seed)
    return next(iter(seller_token_wallet.addresses.keys()))


@pytest.fixture(scope="module")
def trustee_wallets(trustee_data):
    return build_wallets_from_data(trustee_data)


@pytest.fixture(scope="module")
def allPluginsPath(allPluginsPath):
    return allPluginsPath + [getPluginPath('token')]


@pytest.fixture(scope="module")
def testNodeClass(patchPluginManager):
    return update_node_class(TestNode)


@pytest.fixture(scope="module")
def txnPoolNodeSet(txnPoolNodeSet):
    for node in txnPoolNodeSet:
        update_node_obj(node)
    return txnPoolNodeSet


@pytest.fixture(scope="module")
def tokens_distributed(public_minting, seller_token_wallet, seller_address,
                       user1_address, user1_token_wallet,
                       user2_address, user2_token_wallet,
                       user3_address, user3_token_wallet, looper, client1,
                       wallet1, client1Connected):
    register_token_wallet_with_client(client1, seller_token_wallet)
    send_get_utxo(looper, seller_address, wallet1, client1)
    total_amount = seller_token_wallet.get_total_amount(seller_address)

    inputs = [[seller_token_wallet, seller_address, seq_no] for seq_no, _ in
              next(iter(seller_token_wallet.get_all_utxos(seller_address).values()))]
    each_user_share = total_amount // 3
    outputs = [[user1_address, each_user_share],
               [user2_address, each_user_share],
               [user3_address, each_user_share],
               [seller_address, total_amount % 3]]
    req = send_xfer(looper, inputs, outputs, client1)
    for w, a in [(user1_token_wallet, user1_address),
                 (user2_token_wallet, user2_address),
                 (user3_token_wallet, user3_address)]:
        register_token_wallet_with_client(client1, w)
        send_get_utxo(looper, a, wallet1, client1)

    reply, _ = client1.getReply(req.identifier, req.reqId)
    return reply[F.seqNo.name]
