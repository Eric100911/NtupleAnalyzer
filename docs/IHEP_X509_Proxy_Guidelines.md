# IHEP CCEOS X509 proxy guidelines

**Why this exists.** Reading the JJP efficiency input ntuples from IHEP CCEOS
storage requires a valid CMS VOMS proxy. A production bug surfaced when
`condor/run_ihep_efficiency_shard.sh` called `unset X509_USER_PROXY`: the HepJob
workers had no proxy, and every CCEOS read failed with
`[3010] Operation not permitted`. These rules record how to resolve, check,
distribute, and protect the proxy so that failure mode does not recur.

## 1. CCEOS reads require a valid CMS VOMS proxy

CCEOS (`cceos.ihep.ac.cn:1094`, path prefix `root://cceos.ihep.ac.cn:1094///store/...`)
requires a CMS VOMS proxy to read content. Metadata operations such as
`xrdfs stat` of world-readable files can succeed anonymously, but actually
opening/reading file content — `xrdcp`, uproot, ROOT `TFile` — is denied with
`[3010] Operation not permitted` when no proxy is present.

## 2. Resolve the proxy from the environment, never by scanning the filesystem

Resolution order: `$X509_USER_PROXY` first, then `voms-proxy-info --path`.
Warn when the resolved proxy lives under `/tmp` — batch worker nodes cannot
access the submit host's `/tmp`. `common/paths.sh::resolve_proxy_path()` in the
sibling `Full_MC_Production` repo implements exactly this order; mirror it here.

## 3. Check validity on lxplus

On lxplus the current proxy is `/afs/cern.ch/user/c/chiw/condor/x509up` (the
`~/condor/x509up` file). Check it with:

```bash
voms-proxy-info -file /afs/cern.ch/user/c/chiw/condor/x509up --timeleft
```

A healthy proxy has tens of hours left; renew before it gets short.

## 4. Manual CCEOS inspection runs from IHEP lxlogin

Run manual `xrdfs` inspection from ihep (lxlogin), not lxplus. lxlogin sits on
the IHEP LAN and reaches CCEOS far faster than lxplus. After each proxy refresh,
copy the proxy to IHEP under a timestamped directory and point
`X509_USER_PROXY` at the copy:

```bash
# from lxplus, once per proxy refresh
TS=$(date -u +%Y%m%dT%H%M%SZ)
ssh ihep "mkdir -p /scratchfs2/cms/wangchi/hepjobs/NtupleAnalyzer/credentials/$TS/credentials"
scp -q "$X509_USER_PROXY" "ihep:/scratchfs2/cms/wangchi/hepjobs/NtupleAnalyzer/credentials/$TS/credentials/x509_user_proxy"
ssh ihep "chmod 600 /scratchfs2/cms/wangchi/hepjobs/NtupleAnalyzer/credentials/$TS/credentials/x509_user_proxy"

# then on ihep
export X509_USER_PROXY=/scratchfs2/cms/wangchi/hepjobs/NtupleAnalyzer/credentials/$TS/credentials/x509_user_proxy
xrdfs root://cceos.ihep.ac.cn:1094/ ls -R /store/user/chiw/<path>/
```

Convention: one timestamped directory per refresh —
`credentials/<UTC timestamp>/credentials/x509_user_proxy` (mirroring the HepJob
credentials layout).

## 5. In batch workers, use a job-private proxy path

Never install the proxy at the node-shared `/tmp/x509up_u$(id -u)`.
Concurrent same-UID jobs on one node race and overwrite each other:
`install: cannot create regular file ... File exists`. Use a job-private path
and never touch `/tmp`:

```bash
PROXY_TARGET="${PWD}/credentials/x509_user_proxy"
```

`chmod 600` the proxy and never `rm credentials`.

## 6. Before submission, rebuild the proxy bundle idempotently

Recreate the proxy bundle each submission (idempotent) — a tar.gz containing
`credentials/x509_user_proxy`, chmod 600:

```bash
TMP=$(mktemp -d "$WS/.proxy.XXXXXX"); trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/credentials"
install -m 600 "$PROXY_SOURCE" "$TMP/credentials/x509_user_proxy"
tar -czf "$WS/bundles/proxy_bundle.tar.gz.tmp" -C "$TMP" credentials
chmod 600 "$WS/bundles/proxy_bundle.tar.gz.tmp"
mv -f "$WS/bundles/proxy_bundle.tar.gz.tmp" "$WS/bundles/proxy_bundle.tar.gz"
```

Refuse to submit if the proxy has fewer than 10 minutes left
(`voms-proxy-info --timeleft` check).

## 7. Proxy files are secrets

Proxy files are credentials: never commit them to git, never record them in
campaign state or ledger files, never place them under the repo. They live on
AFS (`/afs/cern.ch/...`) and `/scratchfs2` (IHEP) only.
