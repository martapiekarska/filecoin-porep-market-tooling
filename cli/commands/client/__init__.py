from .get_deals import get_deals
from .get_filecoin_pay_account import get_filecoin_pay_account
from .propose_deal_from_manifest import propose_deal_from_manifest
from .propose_deal_from_manifest import propose_deal_from_manifest_mocked
from .init_accepted_deals import init_accepted_deals
from .deposit_for_all_deals import deposit_for_all_deals

from ._client import client, info

client.add_command(info)
client.add_command(get_deals)
client.add_command(get_filecoin_pay_account)
client.add_command(propose_deal_from_manifest)
client.add_command(propose_deal_from_manifest_mocked)
client.add_command(init_accepted_deals)
client.add_command(deposit_for_all_deals)
