# Filecoin PoRep Market tooling CLI

[![cli/test.sh](https://github.com/pingwindyktator/filecoin-porep-market-tooling/actions/workflows/test-sh.yml/badge.svg)](https://github.com/pingwindyktator/filecoin-porep-market-tooling/actions/workflows/test-sh.yml)
[![Code linters](https://github.com/pingwindyktator/filecoin-porep-market-tooling/actions/workflows/lint.yml/badge.svg)](https://github.com/pingwindyktator/filecoin-porep-market-tooling/actions/workflows/lint.yml)
[![CodeQL](https://github.com/pingwindyktator/filecoin-porep-market-tooling/actions/workflows/github-code-scanning/codeql/badge.svg)](https://github.com/pingwindyktator/filecoin-porep-market-tooling/actions/workflows/github-code-scanning/codeql)
[![Copilot code review](https://github.com/pingwindyktator/filecoin-porep-market-tooling/actions/workflows/copilot-pull-request-reviewer/copilot-pull-request-reviewer/badge.svg)](https://github.com/pingwindyktator/filecoin-porep-market-tooling/actions/workflows/copilot-pull-request-reviewer/copilot-pull-request-reviewer)

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

- The app **does not store any state** locally - all state is retrieved from the blockchain by design.
- The app stores all blockchain transaction logs to `logs/`.
- Default behaviour is to wait for each transaction to succeed after sending it.
- The app operates on EVM 0x-addresses and **FEVM smart contract** and does not fully support Filecoin f-addresses.
- There are 3 ways of providing the user's private key for blockchain transactions and the priority is as follows:
    1. `[ADMIN|CLIENT|SP]_PRIVATE_KEY` variable in the system environment variables,
    2. `[ADMIN|CLIENT|SP]_PRIVATE_KEY` variable in the local `.env` file,
    3. if non of those are set, the app will prompt the user to input the private key for required operations in a secure manner.
- The app expects the private key to be 32-byte raw private key (hex, 0x-prefixed).
- Read-only commands do not require private key set, though some of them require user's address.
- To avoid confusion, for all blockchain transactions, the app expects the `--address` option to match provided private key.
- Rule of thumb: the private key you set is the one that signs and sends transactions, \
  so always use the one with correct permissions / approvals / rights for the transaction you want to send.
- There are 2 ways of providing the user's address for blockchain transactions and the priority is as follows:
    1. Derive from the provided private key (if any),
    2. `--address` option. \
       If both are provided, the app expects them to match to avoid confusion.
       For some read-only commands, neither private key nor address is required.
- Make sure the address for blockchain transactions you use has enough FIL for gas fees and is **initialized on the Filecoin network**.
- The app prints output of read-only commands in json format to be easily parsable by other tools.
- PoRep Market smart contracts supports only 32 GiB sectors.
- PoRep Market smart contracts assumes a month is always 30 days.

## Security considerations

- All blockchain transactions **require manual user confirmation** before sending. There is no option to override this. \
  If you decline the final confirmation, the command falls back to dry-run behavior without broadcasting the transaction.
- The app runs locally and does not transmit any data to external servers besides blockchain. \
  All interactions are between the user's machine and the provided `RPC_URL` blockchain.
- The app does not log any sensitive information neither to the console nor to the log files. \
  All transaction logs are stored without any sensitive information.

## Typical workflow

\# TODO

## Glossary

\# TODO

## Developing new CLI commands

- See files in `cli/commands` for examples of how to implement new commands.
- Keep the code clean and simple, follow the existing patterns and best practices.
- Use `Exception` (`ValueError`, `RuntimeError`, ...) for internal-like errors (things that "should not happen")
  and `click.ClickException` for user-like errors (things that happens "because of the user").
- Use `click.echo` for all user-facing output and `logger` for file logging.
- For read-only commands, print the output in json format for easy parsing by other tools.
