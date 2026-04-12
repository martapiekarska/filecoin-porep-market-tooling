from .get_devnet_sps import get_devnet_sps
from .get_deals import get_deals
from .get_db_sps import get_db_sps
from .get_registered_sps import get_registered_sps
from .register_sps import register_db_sps, register_devnet_sps

from ._admin import admin, info

admin.add_command(info)
admin.add_command(get_devnet_sps)
admin.add_command(get_deals)
admin.add_command(get_db_sps)
admin.add_command(get_registered_sps)
admin.add_command(register_db_sps)
admin.add_command(register_devnet_sps)
