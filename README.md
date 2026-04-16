# Filecoin PoRep Market Tooling

Python3 CLI tool for interacting with [Filecoin PoRep Market](https://github.com/fidlabs/porep-market) smart contracts
using [Click](https://click.palletsprojects.com/en/stable/#), [Web3](https://web3py.readthedocs.io/en/stable/) and [psycopg](https://www.psycopg.org/docs/). \
Developed for admins, clients, and SPs to **manage their market interactions** from command line.

## Installation

**Use python >= 3.10**

```bash
python3 -m pip install -r requirements.txt
cp .env.mainnet .env
```

## Running the CLI

Make sure you have the required environment variables (see `.env`). \
Run the script: `python3 ./porep_tooling_cli.py` and follow help prompts.

## Important notes

- The app **does not store any state** locally - all state is retrieved from the blockchain by the design.
- The app stores all blockchain transaction logs to `logs/`.
- All blockchain transactions **require manual user confirmation** before sending. There is no option to override this. \
  If you decline the final confirmation, the command falls back to dry-run behavior without broadcasting the transaction.
- To avoid confusion, for all blockchain transactions, the app expects the `--address` option to match `--private-key` option.
- Default behaviour is to wait for the previous transaction confirmation BEFORE sending the next one and NOT AFTER the transaction. \
  This means that the app does not wait for the transaction receipt after sending it. \
  This behaviour may change in the future.
- Read-only commands does not require confirmations.
- Read-only commands does not require `--private-key` set, though some of them require `--address`.
- The app operates on EVM 0x-addresses and **FEVM smart contract** and does not fully support Filecoin f-addresses.
- There are 3 ways of providing the user's private key for blockchain transactions and the priority is as follows:
    1. `--private-key` option in the command line (not recommended for security reasons),
    2. `[ADMIN|CLIENT|SP]_PRIVATE_KEY` variable in the system environment variables,
    3. `[ADMIN|CLIENT|SP]_PRIVATE_KEY` variable in the local `.env` file. \
       For read-only commands, private key is not required.
- There are 2 ways of providing the user's address for blockchain transactions and the priority is as follows:
    1. Derive from the provided private key (if any),
    2. `--address` option.\
       If both are provided, the app expects them to match to avoid confusion. \
       For some read-only commands, neither private key nor address is required.
- The app prints output of read-only commands in json format to be easily parsable by other tools.
- All commands that requires sending blockchain transactions are manual and interactive.
- PoRep Market smart contracts supports only 32 GiB sectors.
- PoRep Market smart contracts assumes a month is always 30 days.

## Security considerations

- The app runs locally and does not transmit any data to external servers besides blockchain. \
  All interactions are between the user's machine and the provided `RPC_URL` blockchain.
- The app does not log any sensitive information neither to the console nor to the log files. \
  All transaction logs are stored without any sensitive information.
- The only place where private keys should be stored is local `.env` file. \
  **Be aware** that when using `--private-key` option, **the private key may be visible in the command history or process list.** \
  This is a default system behavior and is not specific to this app.

## Developing new CLI commands

See files in `cli/commands` and follow the patterns! Also, see `./cli/test.sh`!
