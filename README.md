# Filecoin PoRep Market Tooling
Python3 CLI tool for interacting with [Filecoin PoRep market](https://github.com/fidlabs/porep-market) smart contracts using [Click](https://click.palletsprojects.com/en/stable/#), [Web3](https://web3py.readthedocs.io/en/stable/) and [psycopg](https://www.psycopg.org/docs/). \
Developed for admins, clients, and SPs to manage their market interactions from command line.


## Installation
Use python >= 3.10.
```bash
python3 -m pip install -r requirements.txt
cp .env.example .env
```


## Running the CLI
Make sure you have the required environment variables (see `.env`). \
Run the script: `python3 ./porep_tooling_cli.py` and follow help prompts.


## Important notes
- All write operations requires confirmation before sending. There is no option to override this. \
If you decline the final confirmation, the command falls back to dry-run behavior for that transaction.
- Default behaviour is to wait for every transaction confirmation BEFORE sending the next one.
- The app operates on ETH 0x addresses and FEVM Smart Contracts and does not fully support Filecoin f-addresses.


## Developing new CLI commands
See files in `cli/commands` and follow the patterns! Also, see `./cli/test.sh`!
