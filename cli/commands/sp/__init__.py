from .get_deals import get_deals
from .accept_deal import accept_deal
from .reject_deal import reject_deal
from .manage_proposed_deals import manage_proposed_deals

from ._sp import sp, info

sp.add_command(info)
sp.add_command(get_deals)
sp.add_command(accept_deal)
sp.add_command(reject_deal)
sp.add_command(manage_proposed_deals)
