# ELK on Kubernetes — Local Teaching Demo

A fully real, locally-runnable demo of log collection on Kubernetes with
**Filebeat → Logstash → Elasticsearch → Kibana**. Nothing is mocked — every
component is a real container producing real data, and the project ships
with 3 pre-built, importable Kibana dashboards (Overview, Errors,
Pods & Infrastructure) so you have something concrete to show from minute
one.

The Kubernetes cluster is created with **Docker Desktop's built-in
Kubernetes feature, using its "kind" provisioning method** — this is the
same underlying [kind](https://kind.sigs.k8s.io/) technology (multi-node
clusters made of Docker containers), just driven from Docker Desktop's GUI
instead of a separate CLI, so there's one less tool to install.

## Architecture

```
demo-app namespace              logging namespace
┌───────────┐                   ┌────────────────────┐
│ frontend  │ stdout logs       │ Filebeat (DaemonSet)│
│ backend   │ ───────────────▶  │  reads hostPath     │
│ worker    │ (via containerd)  │  container logs on  │
└───────────┘                   │  every node          │
                                 └──────────┬───────────┘
                                            │ ships to
                                            ▼
                                 ┌────────────────────┐
                                 │      Logstash        │ parses raw log
                                 │  grok filter parses  │ lines into
                                 │  log_level, service_  │ log_level /
                                 │  name, log_message    │ service_name /
                                 └──────────┬───────────┘ log_message
                                            │
                                            ▼
                                 ┌────────────────────┐        ┌─────────┐
                                 │   Elasticsearch     │◀───────│ Kibana  │
                                 │   (app-logs-* index)│        │ 3 pre-built
                                 └────────────────────┘        │ dashboards
                                                                 └─────────┘
```
## Project layout

```
frontend/                     # Flask service, logs simulated page visits
backend/                      # Flask service, has the deliberate /api/error endpoint
worker/                       # background job loop, logs info/warn/error on its own
k8s/
  01-namespaces.yaml          # demo-app + logging namespaces
  02-backend.yaml             # backend Deployment + Service
  03-frontend.yaml            # frontend Deployment + Service
  04-worker.yaml              # worker Deployment (no Service needed)
  10-elasticsearch.yaml       # single-node Elasticsearch
  11-kibana.yaml               # Kibana, wired to Elasticsearch
  12-filebeat.yaml             # Filebeat DaemonSet, RBAC, autodiscover config
  13-logstash.yaml             # required parsing stage: Filebeat -> here -> Elasticsearch
kibana-dashboards.ndjson      # 3 pre-built dashboards, import in Step 11
```

The Kubernetes cluster itself isn't defined by a file in this project — it's
created through Docker Desktop's Settings UI (see Step 1 below).

## Prerequisites

You need exactly one thing: **Docker Desktop**. It bundles its own `kubectl`,
so there's nothing else to install. Run everything below in **PowerShell**.


Verify it's running:

```powershell
docker version
```

Expect a `Client:` and `Server:` block, both without errors.

Verify `kubectl` came bundled with it:

```powershell
kubectl.exe version --client
```

Expect a `Client Version: v1.3x.x` line. If PowerShell says `kubectl` isn't
recognized, close and reopen your terminal (the installer adds it to PATH,
which existing terminal windows won't pick up until restarted).

> From here on, commands assume you're in this project's root directory.

## Step 1 — Create the cluster via Docker Desktop's Kubernetes settings

1. Open Docker Desktop → **Settings** (gear icon) → **Kubernetes**.
2. Toggle **Enable Kubernetes** on.
3. Under **Cluster settings → Choose cluster provisioning method**, select
   **kind**.
4. Set **Kubernetes version** to something in the 1.30–1.35 range (any recent
   version works).
5. Set **Node(s)** to **3** using the slider.
6. Click **Apply**. This resets any existing cluster/stacks, which is fine
   for a fresh setup.

It takes a few minutes to pull the node images and start everything. Verify
with:

```powershell
kubectl.exe get nodes
```

Expect 3 nodes: `desktop-control-plane`, `desktop-worker`, `desktop-worker2`,
all `STATUS Ready`.

## Step 2 — Raise `vm.max_map_count` (required for Elasticsearch)

Elasticsearch refuses to start unless the host kernel allows at least 262144
memory-mapped areas. This is a host-wide kernel setting, not a per-container
one, so it has to be set on the Docker Desktop VM itself:

```powershell
docker run --rm --privileged --pid=host alpine nsenter -t 1 -m -u -n -i sysctl -w vm.max_map_count=262144
```

Expect output: `vm.max_map_count = 262144`. (Recent Docker Desktop versions
already default to this value — the command is a no-op confirmation in that
case, which is fine.) This setting resets if you restart Docker Desktop — if
Elasticsearch crash-loops later, re-run this command (see Troubleshooting).

## Step 3 — Build the app images and pre-pull the ELK images

**Build the 3 app images.** Docker Desktop's Kubernetes shares its image
store directly with the cluster, so a plain `docker build` is enough — no
separate load/push step, and pods can use the image the moment it's built:

```powershell
docker build -t demo-backend:latest ./backend
docker build -t demo-frontend:latest ./frontend
docker build -t demo-worker:latest ./worker
```

Each ends with `naming to docker.io/library/demo-...:latest`.

**Pre-pull the Elasticsearch/Kibana/Filebeat/Logstash images.** These are
large (500 MB–2.5 GB) and pulled from `docker.elastic.co`. In this Docker
Desktop + kind setup, letting the *worker* nodes pull these directly can be
flaky (large pulls sometimes fail with `short read ... unexpected EOF` on
worker nodes specifically, even though the same image pulls fine on the
control-plane node). Pulling them once through the main Docker engine first
avoids that entirely, since the cluster reads from the same shared image
store:

```powershell
docker pull docker.elastic.co/elasticsearch/elasticsearch:9.4.3
docker pull docker.elastic.co/kibana/kibana:9.4.3
docker pull docker.elastic.co/beats/filebeat:9.4.3
docker pull docker.elastic.co/logstash/logstash:9.4.3
```

This takes a few minutes depending on your connection — each ends with
`Status: Downloaded newer image for ...`.

## Step 4 — Create the namespaces

```powershell
kubectl.exe apply -f k8s/01-namespaces.yaml
```

Expect:

```
namespace/demo-app created
namespace/logging created
```

## Step 5 — Deploy the sample app

```powershell
kubectl.exe apply -f k8s/02-backend.yaml -f k8s/03-frontend.yaml -f k8s/04-worker.yaml
kubectl.exe get pods -n demo-app
```

Wait until all 3 pods show `STATUS Running` and `READY 1/1` — since the
images were just built locally, this is usually just a few seconds (re-run
`kubectl.exe get pods -n demo-app` until they do).

## Step 6 — Deploy Elasticsearch

```powershell
kubectl.exe apply -f k8s/10-elasticsearch.yaml
kubectl.exe get pods -n logging -w
```

The `-w` watches live; press `Ctrl+C` once you see `elasticsearch-... 1/1
Running`. Since the image was already pulled in Step 3, this is mostly just
JVM startup + readiness probe: expect **30–90 seconds**.

## Step 7 — Deploy Kibana

```powershell
kubectl.exe apply -f k8s/11-kibana.yaml
kubectl.exe get pods -n logging -w
```

Again press `Ctrl+C` once `kibana-... 1/1 Running` appears. Kibana itself
takes another 60–90 seconds after `Running` to pass its readiness probe.

## Step 8 — Deploy Logstash

Logstash sits between Filebeat and Elasticsearch and is required for this
pipeline — deploy it before Filebeat so Filebeat has somewhere to send logs
the moment it starts:

```powershell
kubectl.exe apply -f k8s/13-logstash.yaml
kubectl.exe get pods -n logging -l app=logstash -w
```

Press `Ctrl+C` once `logstash-... 1/1 Running` appears — expect 30-60
seconds (JVM startup, same as Elasticsearch).

## Step 9 — Deploy Filebeat

```powershell
kubectl.exe apply -f k8s/12-filebeat.yaml
kubectl.exe get pods -n logging -l app=filebeat -o wide
```

Expect **3 Filebeat pods** (one per node — the DaemonSet includes a
toleration so it also runs on the control-plane), all `1/1 Running`, each on
a different `NODE`.

At this point logs are already flowing through the full pipeline: the
backend, frontend, and worker all log continuously on their own (heartbeats
/ simulated traffic / job loop), Filebeat ships them to Logstash, Logstash
parses them and writes to Elasticsearch — no need to generate traffic
manually before moving on.

## Step 10 — Open Kibana and create a Data View

Port-forward Kibana to your machine (run this in its own PowerShell window —
it blocks, leave it running for the rest of the demo):

```powershell
kubectl.exe port-forward -n logging svc/kibana 5601:5601
```

Expect: `Forwarding from 127.0.0.1:5601 -> 5601`. Open
**http://localhost:5601** in your browser.

In Kibana:

1. Open the hamburger menu → **Stack Management** → **Data Views** (this is
   the modern name for what used to be called "Index Patterns").
2. Click **Create data view**.
3. Name / index pattern: `app-logs-*`
4. Timestamp field: `@timestamp`
5. Click **Save data view to Kibana**.

Go to **Discover** (hamburger menu) and select the `app-logs-*` data view.
You should immediately see a live stream of log documents from `backend`,
`frontend`, and `worker`, each with real parsed fields: `log_level`,
`service_name`, `log_message` — courtesy of Logstash.

## Step 11 — Import the pre-built dashboards

This project ships with `kibana-dashboards.ndjson`: 3 ready-made dashboards
(11 visualizations + 1 saved search) built against this exact data, so you
have something to show immediately instead of building everything from
scratch live.

In Kibana:

1. Hamburger menu → **Stack Management** → **Saved Objects**.
2. Click **Import**.
3. Choose the file `kibana-dashboards.ndjson` from this project's root
   folder.
4. Select **Request action on conflict → Overwrite** (or just leave the
   default — the import is safe to re-run).
5. Click **Import**.

Then go to hamburger menu → **Dashboards** — you'll see 3 dashboards:

**ELK Course - Overview** — the big picture: total log count, a log-level
breakdown (INFO/WARNING/ERROR), a per-service split (backend/frontend/
worker), and log volume over time.

**ELK Course - Errors** — total error count, which service is producing the
most errors, error count trending over time, and a live table of the most
recent error messages (this table updates as new errors happen — refresh
the dashboard's time range to see it move).

**ELK Course - Pods & Infrastructure** — log volume broken down by pod
name, by node, and by namespace, plus log volume over time *split by pod*
— this is the one to watch during the live-demo scaling exercise below,
since new pod names appear in it automatically.

All 3 dashboards use the `app-logs-*` data view created in Step 10 — if you
ever recreate that data view under a different name, re-point the
dashboards via **Stack Management → Saved Objects** before they'll render.

---

## Live demo

Keep the Kibana port-forward from Step 10 running in its own window for all
of this. Have the **ELK Course - Pods & Infrastructure** and
**ELK Course - Errors** dashboards open in browser tabs.

### 1. Scale the app and watch new pods appear automatically

```powershell
kubectl.exe scale deployment worker -n demo-app --replicas=4
kubectl.exe get pods -n demo-app -l app=worker
```

You'll see 4 worker pods with different names. Refresh the
**ELK Course - Pods & Infrastructure** dashboard (or widen its time range)
— the "Log Volume by Pod" chart picks up the new pod names within seconds,
with **zero Filebeat or Logstash configuration changes**. That's
autodiscover doing its job.

You can also check this directly in Kibana Discover, data view
`app-logs-*`, search:

```
kubernetes.labels.app : "worker"
```

Expand a document and look at `kubernetes.pod.name` to confirm.

### 2. Delete a pod and confirm its logs still persist

```powershell
kubectl.exe get pods -n demo-app -l app=worker
```

Copy one of the pod names, then:

```powershell
kubectl.exe delete pod <paste-pod-name-here> -n demo-app
kubectl.exe logs <paste-pod-name-here> -n demo-app
```

The second command fails (`Error from server (NotFound)`) — the pod and its
container logs are gone from the node. But in Kibana Discover, search:

```
kubernetes.pod.name : "<paste-pod-name-here>"
```

The documents are still there — Elasticsearch has its own durable copy,
independent of the pod's lifecycle.

### 3. Hit the error endpoint and watch the Errors dashboard move

In a **new** PowerShell window, port-forward the backend:

```powershell
kubectl.exe port-forward -n demo-app svc/backend 8080:80
```

In a third window, generate some errors and some normal traffic:

```powershell
curl.exe http://localhost:8080/api/error
curl.exe http://localhost:8080/api/error
curl.exe http://localhost:8080/api/orders
```

Refresh the **ELK Course - Errors** dashboard — "Total Errors" ticks up,
"Errors by Service" shows `backend`, and the "Recent Errors" table shows
the exact message (`order processing failed: payment gateway timeout`).

You can also do this in Discover directly. Because Logstash parsed the raw
log line into a real `log_level` field, you can filter structurally instead
of doing a text search:

```
log_level: ERROR and kubernetes.labels.app : "backend"
```

Click **Save** (top toolbar) and name it something like `Backend Errors` —
that's a reusable filtered view you can pull up any time, independent of
the pre-built dashboards.

---
---

## Cleanup

Two levels, depending on how much you want to tear down.

**Light cleanup — remove just this demo's resources, keep Kubernetes
running** (fastest option; use this between demo runs):

```powershell
kubectl.exe delete namespace demo-app logging
```

This deletes every Deployment, Service, DaemonSet, and all Elasticsearch
data with it (it was stored in `emptyDir`, so this is expected and total —
including the imported dashboards' underlying data, though the dashboards
themselves live in Elasticsearch's `.kibana*` indices and will also be
gone; re-import `kibana-dashboards.ndjson` after rebuilding). Verify:

```powershell
kubectl.exe get namespaces
```

`demo-app` and `logging` should be gone (or `Terminating` briefly).

**Full teardown — remove the entire Kubernetes cluster:**

1. Open Docker Desktop → **Settings** → **Kubernetes**.
2. Toggle **Enable Kubernetes** off, then **Apply & Restart**.

This deletes all 3 node containers and everything running inside them.
Turning it back on later re-creates a fresh 3-node cluster using whatever
`Node(s)` value is still set (leave it at 3 for next time).

Optionally remove the locally built/pulled images:

```powershell
docker rmi demo-backend:latest demo-frontend:latest demo-worker:latest
docker rmi docker.elastic.co/elasticsearch/elasticsearch:9.4.3 docker.elastic.co/kibana/kibana:9.4.3 docker.elastic.co/beats/filebeat:9.4.3 docker.elastic.co/logstash/logstash:9.4.3
```

The `vm.max_map_count` kernel setting from Step 2 does **not** need to be
reverted — it's a harmless setting to leave in place, and it resets on its
own next time Docker Desktop restarts.
