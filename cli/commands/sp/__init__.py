from ._sp import sp, info
from .accept_deal import accept_deal
from .get_deals import get_deals
from .manage_proposed_deals import manage_proposed_deals
from .reject_deal import reject_deal

sp.add_command(info)
sp.add_command(get_deals)
sp.add_command(accept_deal)
sp.add_command(reject_deal)
sp.add_command(manage_proposed_deals)
