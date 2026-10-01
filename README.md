# Filecoin PoRep Market tooling CLI

[![cli/test.sh](https://github.com/fidlabs/filecoin-porep-market-tooling/actions/workflows/test-sh.yml/badge.svg)](https://github.com/fidlabs/filecoin-porep-market-tooling/actions/workflows/test-sh.yml)
[![Code linters](https://github.com/fidlabs/filecoin-porep-market-tooling/actions/workflows/lint.yml/badge.svg)](https://github.com/fidlabs/filecoin-porep-market-tooling/actions/workflows/lint.yml)
[![CodeQL](https://github.com/fidlabs/filecoin-porep-market-tooling/actions/workflows/github-code-scanning/codeql/badge.svg)](https://github.com/fidlabs/filecoin-porep-market-tooling/actions/workflows/github-code-scanning/codeql)
[![Copilot code review](https://github.com/fidlabs/filecoin-porep-market-tooling/actions/workflows/copilot-pull-request-reviewer/copilot-pull-request-reviewer/badge.svg)](https://github.com/fidlabs/filecoin-porep-market-tooling/actions/workflows/copilot-pull-request-reviewer/copilot-pull-request-reviewer)

Python3 CLI tool for interacting with [Filecoin PoRep Market](https://github.com/fidlabs/porep-market) smart contracts
using [Click](https://click.palletsprojects.com/en/stable/#), [Web3](https://web3py.readthedocs.io/en/stable/) and [psycopg](https://www.psycopg.org/docs/). \
Developed for admins, clients, and SPs to **manage their market interactions** from command line.

## Installation

**Use python >= 3.10**

```bash
python3 --version  # check your python version
git clone https://github.com/fidlabs/filecoin-porep-market-tooling && cd filecoin-porep-market-tooling  # clone the repo
python3 -m pip install -r requirements.txt  # install dependencies
cp .env.mainnet .env  # create your local .env file
chmod 600 .env  # optional, but recommended for security: restrict access to the .env file
```

## Running the CLI

Make sure you have the required environment variables set (see `.env`). \
Run the script: `python3 ./porep_tooling_cli.py` and follow help prompts.

## Important notes

- The app **does not store any state** locally - all state is retrieved from the blockchain by design.
- The app stores all blockchain transaction logs to `logs/`.
- Default behaviour is to wait for each transaction to succeed after sending it.
- The app operates on **FEVM smart contracts** (thus EVM 0x-addresses) but **fully supports Filecoin f-addresses / Actor IDs** with proper conversion.
- There are multiple ways of providing the user's private key for blockchain transactions and the priority is as follows:
    1. `[ADMIN|CLIENT|SP]_PRIVATE_KEY` variable in the system environment variables or in the local `.env` file,
    2. `[ADMIN|CLIENT|SP]_LOTUS_WALLET` and `[ADMIN|CLIENT|SP]_LOTUS_TOKEN` variables when using Lotus wallet,
    3. if non of those are set, the app will prompt the user to input the private key for required operations in a secure manner.
- Read-only commands do not require private key / lotus wallet set, though some of them require user's address (`client --address` and `sp --organization`).
- Rule of thumb: the private key / lotus wallet you set is the one that signs and sends transactions, \
  so always use the one with correct permissions / approvals / rights for the transaction you want to send.
- Make sure the address for blockchain transactions you use has enough FIL for gas fees and is **initialized on the Filecoin network**.
- The app prints output of read-only commands in json format to be easily parsable by other tools.
- PoRep Market smart contracts supports only 32 GiB sectors.
- PoRep Market smart contracts assumes a month is always 30 days.

## Security considerations

- All blockchain transactions **require manual user confirmation** before sending. There is no option to override this. \
  If you decline the final confirmation, the command falls back to dry-run behavior without broadcasting the transaction.
- The app runs locally and does not transmit any data to external servers besides blockchain.
  All interactions are between the user's machine and the provided `RPC_URL` blockchain.
- The app does not log any sensitive information to the console or to the log files.
  All transaction logs are stored without any sensitive information.
- When using Lotus wallet for blockchain transaction signing, the **private key never leaves the Lotus wallet** and is not exposed to the CLI app. \
  This is the recommended way of using the app.

## Typical SP workflow

1. Follow the [Installation](#installation) steps.

2. Steps 3-5 below are required for SP to make blockchain _write_ transactions (such as `sp register-offer`).
   You won't need this in a typical SP flow.

3. **IMPORTANT**: interaction with the chain requires the private key for the message sender,
   so for security do not use your miner wallet for sending commands to the PoRep Market. \
   Instead, you will need to create a _miner controller_ wallet. If you already have one and want to reuse it, that’s fine. \
   However, to follow best security practices, we recommend you create a new wallet and register it as a _controller wallet_
   for all the miners you will be using in the PoRep Market. \
   The PoRep Market then uses controller status to verify that the command sender is authorised to send commands on behalf of your miner. \
   Follow the steps here:
   [https://lotus.filecoin.io/storage-providers/operate/addresses/#control-addresses](https://lotus.filecoin.io/storage-providers/operate/addresses/#control-addresses)

4. Export the private key of your newly created wallet:

   ```bash
   lotus wallet export <your-controller-address> | xxd -r -p | jq -r '.PrivateKey' | base64 -d | xxd -p -c 32 | sed 's/^/0x/'
   ```

   And set it as `SP_PRIVATE_KEY` in your `.env` file. The value you store there
   must be this exported private key in 32-byte hex format with a `0x` prefix - **not** the wallet
   address you pass to `lotus wallet export`

5. Alternatively, generate an auth token for your _controller address_ and use it instead of the private key:

    ```bash
    lotus auth create-token --perm sign --wallet <your-controller-address>
    ```

   And set it as `SP_LOTUS_TOKEN` in your `.env` file alongside `SP_LOTUS_WALLET` with the address of your _controller wallet_. \
   Using this method, the private key never leaves the Lotus wallet and is not exposed to the CLI app.
   You must use _f410 address_ or _standard EVM address_ for this method.

6. Set your SP organization address in `.env`:

      ```bash
      # Organization address to manage SPs from
      # You must have the SP_PRIVATE_KEY of an organization controlling address set to perform SP management operations
      
      SP_ORGANIZATION=<your-controller-address>
      ```

7. Optional, but very useful for downloading the deal data: install `aria2`:
    - on Mac `brew install aria2`
    - on Debian/Ubuntu: `sudo apt install aria2`
    - on Arch: `sudo pacman -S aria2`

8. Now you should be ready to run the tools.
    - to find deals allocated to you and ready to download / onboard:

      ```bash
      python3 ./porep_tooling_cli.py sp get-deals ACTIVE
      ```

    - to download / onboard the deal that is allocated to you:

      ```bash
      python3 ./porep_tooling_cli.py sp onboard-data <deal-id> --output-dir <dir-to-download-to>
      ``` 

    - get the deal allocation IDs:

      ```bash
      python3 ./porep_tooling_cli.py sp get-allocations <deal-id>
      ``` 

    - and claim allocations for a deal:

      ```bash
      python3 ./porep_tooling_cli.py sp claim-allocations {curio|boost} <deal-id> 
      ```

9. To get the full list of commands for the tooling:

    ```bash
    python3 ./porep_tooling_cli.py sp --help
    ```

## Typical PoRep Market Client workflow

1. Follow the [Installation](#installation) steps.

2. Put your client keys in the `.env` file:

   ```bash
   # Use `lotus wallet list` to see your wallets and their addresses and `lotus wallet new delegated` to create new delegated wallet
   # Must be delegated f410 address or standard EVM address
   CLIENT_LOTUS_WALLET=<lotus-wallet>
   
   # Generate this by running `lotus auth create-token --perm sign`
   CLIENT_LOTUS_TOKEN=<lotus-token>
   ```

   or

   ```bash
   # 32-byte raw private key (hex, 0x-prefixed)
   CLIENT_PRIVATE_KEY=<private key>
   ```

3. Prepare your dataset with [Singularity](https://github.com/filecoin-project/singularity) (or equivalent) so you have a published **manifest URL** and piece
   CARs served for the SP to fetch.

4. Propose a deal from that manifest. Deals can be **public** (open retrieval) or **private** (retrieval limited to the deal owner and any wallets you later
   authorize with a voucher):

   ```bash
   python3 ./porep_tooling_cli.py client propose-deal <manifest-url> \
     --price-per-tib-per-month <usdc-in-decimal-format> \
     --duration-months <months> \
     --retrievability-pct <pct> \
     --bandwidth-mbps <mbps> \
     --latency-ms <ms> \
     --indexing-pct <pct> \
     --deal-type <public|private>
   ```

5. Initialize payment (validator, deposit, rail):

   ```bash
   python3 ./porep_tooling_cli.py client init-deal <deal-id>
   ```

6. Make DataCap allocations:

   ```bash
   python3 ./porep_tooling_cli.py client make-allocations <deal-id>
   ```

7. Optional - for a **private** deal, sign an EIP-712 retrieval voucher so a third-party wallet can retrieve the data (used
   with [large-paid-retrievals](https://github.com/fidlabs/large-paid-retrievals)):

   ```bash
   python3 ./porep_tooling_cli.py client sign-retrieval-voucher \
     --grantee <0x-third-party-wallet> \
     --scope <DEAL_ID>
   ```

   Prints a long-lived standalone `RetrievalVoucher` token (`grantee`, `scope`, `issuedAt`,
   `deadline`, embedded `signature`) for `Authorization: RetrievalVoucher`. \
   Clients mint a per-piece `RetrievalProof` and send it as `Authorization: RetrievalProof` —
   see [access-vouchers-eip712](https://github.com/fidlabs/large-paid-retrievals/blob/main/docs/access-vouchers-eip712.md). \
   `--deal-id` is accepted as an alias for `--scope`.

## FCSS repair flow (re-onboard a dataset from a healthy SP)

FCSS requires two SP copies of every dataset. When one SP exits, the client repairs the dataset with a new deal: a
**new SP**, matched by the market like for any other deal, fetches the data from the **healthy SP** (the one still
serving a copy), paying for that retrieval with [large-paid-retrievals](https://github.com/fidlabs/large-paid-retrievals)
(LPR) where needed. The client pays for that one-off retrieval up front, so the new SP never fronts the cost. No keys
are shared and the client, the new SP and the healthy SP don't need to exchange anything outside the CLI and the chain.

**Finding the healthy SP:** the CLI looks for other providers' deals for the same dataset (same manifest hash) that are
ACTIVE, PUBLIC and have claims on-chain. It then checks each provider's advertised HTTP piece endpoint (cid.contact,
else the miner's on-chain multiaddrs, the same discovery LPR uses) actually serves sample pieces of the expected size.
Free sources are preferred, then the cheapest. Both the client and the new SP do this on their own.

**Finding the price:** the healthy SP's LPR `sp-proxy` answers an unpaid piece request with `402 Payment Required` and
an MPP challenge quoting the piece price ([protocol](https://github.com/fidlabs/large-paid-retrievals/blob/main/docs/mpp-filecoinpay.md)).
The CLI reads the price per GiB from those quotes and applies LPR's pricing (`ceil(fileSize / GiB) × price` per piece)
to the whole manifest. If the healthy SP serves the data for free, there is nothing to pay.

**How the retrieval payment works:** the LPR `sp-proxy` only accepts a Filecoin Pay one-time rail payment whose payer is
the wallet that signs the retrieval request, i.e. the wallet that downloads. So the client cannot pay the healthy SP
on the new SP's behalf. Instead, `client propose-deal --repair` (or `client pay-repair-retrieval`) makes a one-off
FileCoinPay `deposit` of the retrieval cost **into the FileCoinPay account of the new deal's SP payee**. That is the
payee address the SP registered with `sp register-sp --payee-address`, recorded on-chain in the deal. The new SP runs
LPR `retrieval-client` with the payee key, and it spends available FileCoinPay funds before using any wallet balance,
so the new SP's download is paid by the client. The client's exposure is capped at the deposited amount; the deposit
is separate from and in addition to the regular deal payment rail (`client init-deal`).

1. **Healthy SP:** if it charges for retrievals, it runs LPR `sp-proxy` in front of its piece server with a flat
   `--price-usdfc-per-gb` rate, following [LPR for storage providers](https://github.com/fidlabs/large-paid-retrievals#for-storage-providers).
   As LPR requires, its advertised HTTP endpoint must point at the `sp-proxy`.

2. **Client:** propose the new deal with `--repair`, from the repaired deal's manifest URL:

   ```bash
   python3 ./porep_tooling_cli.py client propose-deal <repaired-deal-manifest-url> ... \
     --repair \
     --repair-of <repaired-deal-id>
   ```

   This checks the manifest matches the repaired deal, finds the healthy SP and shows the estimated repair cost before
   the proposal is confirmed. The deal is then proposed and matched to an SP **exactly like any other deal**: clients
   can't choose the SP. Once it's matched, the cost is deposited into that SP's payee account. Continue with
   `client init-deal` and `client make-allocations` as usual.

   `--repair-source-url` and `--repair-price-per-gib` override the detected source and price, e.g. when no healthy SP
   is advertised on-chain. `client pay-repair-retrieval <new-deal-id> --repair-of <repaired-deal-id>` runs the deposit
   step on its own, e.g. to retry it. It warns if the client already deposited to that payee since the deal was
   proposed. This check is best effort: some RPC providers only serve the last 24h of logs.

3. **New SP:** build LPR `retrieval-client`
   ([for dataset consumers](https://github.com/fidlabs/large-paid-retrievals#for-dataset-consumers)), put it in `PATH`
   or set `RETRIEVAL_CLIENT_PATH`, and onboard the data through LPR instead of aria2:

   ```bash
   git clone https://github.com/fidlabs/large-paid-retrievals && cd large-paid-retrievals
   go build -o bin/retrieval-client ./cmd/retrieval-client
   ```

   ```bash
   python3 ./porep_tooling_cli.py sp onboard-data <new-deal-id> --output-dir <dir> \
     --downloader lpr --payee-key-file ./payee.key
   ```

   The CLI finds the healthy SP itself (`--host` / `--port` override it), and checks that the key belongs to the
   deal's payee before downloading. The payee must be a regular `0x` wallet, not a contract, with a little FIL for
   Filecoin Pay gas. `retrieval-client` gets the CLI's `RPC_URL`, `FILECOIN_PAY` and the deal's payment token, so it
   spends from the same FileCoinPay account the client funded. In `tools/sp-pipeline.sh`, set
   `ONBOARD_DATA_DOWNLOADER="lpr"` and `PAYEE_KEY_FILE`.

### Legacy (v1) repair with a manually chosen source

Datasets from the v1 PoRep market are repaired onto a regular v2 deal. The CLI doesn't read v1 contracts, so the client
supplies the dataset's original manifest and the healthy source, and nothing is looked up or detected:

1. **Client:** prepare the repair manifest from the original manifest and the healthy SP's piece server / `sp-proxy`
   URL. The original manifest can be a local file, a manifest URL, or a [toads.directory](https://toads.directory/)
   dataset page:

   ```bash
   python3 ./porep_tooling_cli.py client prepare-legacy-repair https://toads.directory/dataset/<id> \
     --repair-source-url https://<healthy-sp-host>:<port>
   ```

   toads.directory serves data-prep-standard super-manifests, which are converted to this CLI's manifest format: each
   piece's `fileSize` is its CAR size, `pieceSize` its minimal padded size, and the smallest piece is the DAG piece.
   The source is embedded in the manifest (`repairSource`), so the new SP knows where to fetch from. The command
   checks the source serves the data at the expected sizes and shows the estimated retrieval cost.

2. **Client:** host the written manifest at any URL and propose the deal. The SP is matched like for any other deal, and
   the retrieval cost is paid into its payee account as for `--repair`:

   ```bash
   python3 ./porep_tooling_cli.py client propose-deal <hosted-repair-manifest-url> ... \
     --repair-legacy \
     --repair-source-url https://<healthy-sp-host>:<port>
   ```

   `--repair-source-url` must match the source embedded in the manifest. `client pay-repair-retrieval <new-deal-id>`
   retries the payment step and picks up the embedded source.

3. **New SP:** `sp onboard-data <new-deal-id> --downloader lpr ...` (or `aria2` if the source serves for free) fetches
   from the embedded source; `--host` / `--port` override it.

A source that doesn't serve the dataset's pieces, such as an SP that is down, is refused.

To have a specific SP store the repair copy, an admin proposes the deal with `admin propose-deal-for-offer`, and the
client then runs `client pay-repair-retrieval`. Choosing an SP is an admin-only action.

Limitations:

- LPR currently lets only the deal owner retrieve **private** deals, so only **public** deals can be repaired. The
  `client sign-retrieval-voucher` integration depends on LPR's unmerged voucher-based access.
- Health is judged from on-chain deal state, claims and a live probe of sample pieces. The CLI does not check sector
  faults or proving status directly.
- LPR has no price endpoint, so the price is read from `402` quotes for sample pieces. Each probe makes the `sp-proxy`
  store an unpaid quote, which it prunes after its retention period.
- The payee's FileCoinPay account also collects the SP's deal earnings, and LPR has no spend cap. If the `sp-proxy`
  quotes more than the estimate, for example after a price change, `retrieval-client` covers the difference from
  those funds or the payee wallet's USDFC.
- LPR can't sign through a Lotus wallet, so the payee key must be available as a plain key file on the downloading host.

## Developing new CLI commands

- See files in `cli/commands` for examples of how to implement new commands.
- Keep the code clean and simple, follow the existing patterns and best practices.
- Use `Exception` (`ValueError`, `RuntimeError`, ...) for internal-like errors (things that "should not happen")
  and `click.ClickException` for user-like errors (things that happens "because of the user").
- Use `click.echo` for all user-facing output and `logger` for file logging.
- For read-only commands, print the output in json format for easy parsing by other tools.
