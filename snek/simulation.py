import collections
import heapq
import warnings

import numpy as np
import pandas as pd

from snek.distributions import draw_values, random_data


class Sampler:
    def __init__(self, rng, dist, params, size=2048):
        self.rng, self.dist, self.params, self.size = rng, dist, params, size
        self.buffer, self.at = [], 0

    def next(self):
        if self.at >= len(self.buffer):
            self.buffer = draw_values(self.rng, self.dist, self.params, self.size).tolist()
            self.at = 0
        value = self.buffer[self.at]
        self.at += 1
        return max(float(value), 0.0)


def build_stations(specs):
    if not specs:
        raise ValueError("Add at least one station")
    names = [str(s.get("name") or "").strip() for s in specs]
    if "" in names:
        raise ValueError("Every station needs a name")
    if len({n.lower() for n in names}) != len(names):
        raise ValueError("Two stations have the same name")
    for n in names:
        if ":" in n or "," in n:
            raise ValueError(f"Station names cannot contain a colon or a comma: {n}")
    lookup = {n.lower(): i for i, n in enumerate(names)}
    built = []
    for i, spec in enumerate(specs):
        routes = []
        for part in [p.strip() for p in str(spec.get("next") or "").split(",") if p.strip()]:
            label, sep, weight = part.rpartition(":")
            value = 1.0
            if sep:
                try:
                    value = float(weight)
                except ValueError:
                    label = part
            else:
                label = part
            label = label.strip().lower()
            if value < 0:
                raise ValueError(f"{names[i]}: a route weight cannot be negative")
            target = -1 if label in ("exit", "") else lookup.get(label)
            if target is None:
                raise ValueError(f"{names[i]}: the next station '{label}' is not in the list. Use a station name or Exit.")
            routes.append((target, value))
        total = sum(w for _, w in routes)
        if routes and total <= 0:
            raise ValueError(f"{names[i]}: the route weights add up to 0")
        cumulative, running = [], 0.0
        for target, w in routes:
            running += w / total
            cumulative.append((running, target))
        servers = int(spec.get("servers") or 1)
        if servers < 0:
            raise ValueError(f"{names[i]}: servers cannot be negative")
        capacity = spec.get("capacity")
        capacity = None if capacity in (None, "") else int(capacity)
        if capacity is not None and capacity < 0:
            raise ValueError(f"{names[i]}: waiting spaces cannot be negative")
        params = [spec.get(k) for k in ("p1", "p2", "p3")]
        params = [float("nan") if v in (None, "") else float(v) for v in params]
        built.append({"name": names[i], "servers": servers, "capacity": capacity, "dist": spec.get("dist") or "constant", "params": params, "scale_by": str(spec.get("scale_by") or "").strip(), "block": bool(spec.get("block")), "routes": cumulative})
    return built


class Sim:
    def __init__(self, stations, rng, warmup, until, keep_log, log_cap, rep):
        self.stations, self.rng, self.warmup, self.until = stations, rng, float(warmup), until
        self.keep_log, self.log_cap, self.rep = keep_log, log_cap, rep
        n = len(stations)
        self.samplers = [Sampler(rng, s["dist"], s["params"]) for s in stations]
        self.servers = [s["servers"] for s in stations]
        self.queue = [collections.deque() for _ in range(n)]
        self.blocked = [collections.deque() for _ in range(n)]
        self.busy = [0] * n
        self.area_queue = [0.0] * n
        self.area_serving = [0.0] * n
        self.area_blocked = [0.0] * n
        self.area_servers = [0.0] * n
        self.max_queue = [0] * n
        self.clock = 0.0
        self.last = 0.0
        self.heap = []
        self.seq = 0
        self.visits = []
        self.current = {}
        self.outcome = {}
        self.exit_time = {}
        self.hops = {}
        self.attrs = []
        self.log = []
        self.log_full = False

    def push(self, t, priority, kind, data):
        self.seq += 1
        heapq.heappush(self.heap, (t, priority, self.seq, kind, data))

    def note(self, t, event, entity, station):
        if not self.keep_log:
            return
        if len(self.log) >= self.log_cap:
            self.log_full = True
            return
        s = station if station is not None else -1
        self.log.append((self.rep, t, event, entity, self.stations[s]["name"] if s >= 0 else "", len(self.queue[s]) if s >= 0 else 0, self.busy[s] if s >= 0 else 0))

    def advance(self, t):
        lo, hi = max(self.last, self.warmup), max(t, self.warmup)
        if hi > lo:
            dt = hi - lo
            for s in range(len(self.stations)):
                self.area_queue[s] += len(self.queue[s]) * dt
                held = len(self.blocked[s])
                self.area_serving[s] += (self.busy[s] - held) * dt
                self.area_blocked[s] += held * dt
                self.area_servers[s] += self.servers[s] * dt
        self.last = max(self.last, t)
        self.clock = max(self.clock, t)

    def can_accept(self, s):
        free = self.busy[s] < self.servers[s] and not self.queue[s]
        cap = self.stations[s]["capacity"]
        return free or cap is None or len(self.queue[s]) < cap

    def multiplier(self, e, s):
        column = self.stations[s]["scale_by"]
        return 1.0 if not column else float(self.attrs[e][column])

    def try_start(self, s, t):
        while self.busy[s] < self.servers[s] and self.queue[s]:
            e = self.queue[s].popleft()
            self.busy[s] += 1
            self.current[e]["start"] = t
            self.note(t, "start service", e, s)
            self.push(t + self.samplers[s].next() * self.multiplier(e, s), 2, "end", (e, s))

    def arrive(self, e, s, t):
        hops = self.hops.get(e, 0) + 1
        if hops > 1000:
            raise ValueError("An entity visited more than 1000 stations. Check the next-station routes for a loop that cannot end.")
        self.hops[e] = hops
        visit = {"e": e, "s": s, "arrive": t, "start": np.nan, "end": np.nan, "leave": np.nan}
        self.visits.append(visit)
        self.current[e] = visit
        self.note(t, "arrive", e, s)
        if not self.can_accept(s):
            visit["leave"] = t
            self.outcome[e] = f"lost at {self.stations[s]['name']}"
            self.exit_time[e] = t
            self.note(t, "lost", e, s)
            return
        self.queue[s].append(e)
        self.try_start(s, t)
        if t >= self.warmup:
            self.max_queue[s] = max(self.max_queue[s], len(self.queue[s]))

    def choose(self, s):
        routes = self.stations[s]["routes"]
        if not routes:
            return -1
        u = self.rng.random()
        for edge, target in routes:
            if u < edge:
                return target
        return routes[-1][1]

    def depart(self, e, s, t, outcome):
        self.current[e]["leave"] = t
        self.busy[s] -= 1
        if outcome:
            self.outcome[e] = outcome
            self.exit_time[e] = t
        self.note(t, "lost" if outcome.startswith("lost") else "depart", e, s)
        self.try_start(s, t)

    def end_service(self, e, s, t):
        self.current[e]["end"] = t
        self.note(t, "end service", e, s)
        target = self.choose(s)
        if target == -1:
            self.depart(e, s, t, "served")
        elif self.can_accept(target):
            self.depart(e, s, t, "")
            self.arrive(e, target, t)
        elif self.stations[s]["block"]:
            self.blocked[s].append((t, e, target))
            self.note(t, "blocked", e, s)
        else:
            self.depart(e, s, t, f"lost at {self.stations[target]['name']}")

    def unblock(self, t):
        moved = True
        while moved:
            moved = False
            heads = sorted((self.blocked[s][0][0], s) for s in range(len(self.stations)) if self.blocked[s])
            for _, s in heads:
                _, e, target = self.blocked[s][0]
                if self.can_accept(target):
                    self.blocked[s].popleft()
                    self.depart(e, s, t, "")
                    self.arrive(e, target, t)
                    moved = True
                    break

    def run(self, arrival_times, schedule):
        for e, t in enumerate(arrival_times):
            self.push(float(t), 1, "arrive", e)
        for s, t, n in schedule:
            self.push(float(t), 0, "capacity", (s, n))
        while self.heap:
            t, _, _, kind, data = heapq.heappop(self.heap)
            if self.until is not None and t > self.until:
                break
            self.advance(t)
            if kind == "arrive":
                self.arrive(data, 0, t)
            elif kind == "end":
                self.end_service(data[0], data[1], t)
            else:
                self.servers[data[0]] = data[1]
                self.note(t, f"servers set to {data[1]}", None, data[0])
                self.try_start(data[0], t)
            self.unblock(t)
        self.advance(self.until if self.until is not None else self.clock)


def generate_arrivals(rng, gap, rates, until, attributes):
    if until is None:
        raise ValueError("Set the run length. Arrivals are generated up to that time.")
    times = []
    if rates is not None and len(rates):
        table = rates.sort_values("start").reset_index(drop=True)
        for i, row in table.iterrows():
            start = float(row["start"])
            end = float(table.loc[i + 1, "start"]) if i + 1 < len(table) else float(until)
            mean = float(row["mean_gap"])
            if mean <= 0:
                raise ValueError("Every mean gap in the rates table must be above 0")
            t = start
            while True:
                t += rng.exponential(mean)
                if t >= min(end, until):
                    break
                times.append(t)
                if len(times) > 5_000_000:
                    raise ValueError("More than 5,000,000 arrivals. Check the gaps and the run length.")
    else:
        params = [float("nan") if v in (None, "") else float(v) for v in gap["params"]]
        sampler = Sampler(rng, gap["dist"], params)
        t = 0.0
        while True:
            t += sampler.next()
            if t > until:
                break
            times.append(t)
            if len(times) > 5_000_000:
                raise ValueError("More than 5,000,000 arrivals. Check the gaps and the run length.")
    frame = pd.DataFrame({"arrival_time": times})
    if attributes:
        extra = random_data(len(times), attributes, seed=int(rng.integers(2**31 - 1)))
        frame = pd.concat([frame, extra], axis=1)
    return frame


def simulate_process(arrivals, stations, schedule=None, rates=None, gap=None, attributes=None, until=None, warmup=0.0, replications=1, seed=1, keep_log=False, max_log=200000, time_column="arrival_time", id_column=""):
    from scipy import stats

    built = build_stations(stations)
    names = [s["name"] for s in built]
    lookup = {n.lower(): i for i, n in enumerate(names)}
    replications = int(replications)
    if replications < 1:
        raise ValueError("Run at least 1 replication")
    until = None if until in (None, "") else float(until)
    warmup = float(warmup or 0)
    if until is not None and warmup >= until:
        raise ValueError("The warm-up must be shorter than the run length")
    changes = []
    if schedule is not None and len(schedule):
        for col in ("station", "time", "servers"):
            if col not in schedule.columns:
                raise ValueError(f"The schedule table needs a column named {col}")
        for _, row in schedule.iterrows():
            s = lookup.get(str(row["station"]).strip().lower())
            if s is None:
                raise ValueError(f"The schedule names a station that is not in the list: {row['station']}")
            changes.append((s, float(row["time"]), int(row["servers"])))
    table = None
    if arrivals is not None:
        if time_column not in arrivals.columns:
            raise ValueError(f"The arrivals table needs a column named {time_column}")
        table = arrivals.copy()
        table[time_column] = pd.to_numeric(table[time_column], errors="coerce")
        if table[time_column].isna().any():
            raise ValueError(f"{time_column} has values that are not numbers")
        table = table.sort_values(time_column, kind="stable").reset_index(drop=True)
        if id_column and id_column not in table.columns:
            raise ValueError(f"The arrivals table has no column named {id_column}")
        id_check = id_column or ("entity_id" if "entity_id" in table.columns else "")
        if id_check and table[id_check].duplicated().any():
            raise ValueError(f"{id_check} has repeated values. Each entity needs its own ID.")
        for s in built:
            if s["scale_by"]:
                if s["scale_by"] not in table.columns:
                    raise ValueError(f"{s['name']}: the arrivals table has no column named {s['scale_by']}")
                if not pd.api.types.is_numeric_dtype(table[s["scale_by"]]):
                    raise ValueError(f"{s['name']}: {s['scale_by']} is not numeric")
    else:
        attr_names = [a["name"] for a in (attributes or [])]
        for s in built:
            if s["scale_by"] and s["scale_by"] not in attr_names:
                raise ValueError(f"{s['name']}: there is no attribute named {s['scale_by']}")
        if gap is None and (rates is None or not len(rates)):
            raise ValueError("Connect an arrivals table, or set how far apart arrivals are")
    children = np.random.SeedSequence(int(seed)).spawn(replications)
    ent_frames, visit_frames, station_rows, logs, ends = [], [], [], [], {}
    log_full = False
    for rep in range(1, replications + 1):
        rng = np.random.default_rng(children[rep - 1])
        data = table.copy() if table is not None else generate_arrivals(rng, gap, rates, until, attributes)
        time_col = time_column if table is not None else "arrival_time"
        times = data[time_col].to_numpy(dtype=float)
        sim = Sim(built, rng, warmup, until, keep_log, int(max_log), rep)
        sim.attrs = data.drop(columns=[time_col]).to_dict("records")
        sim.run(times, changes)
        log_full = log_full or sim.log_full
        logs += sim.log
        end = until if until is not None else sim.clock
        ends[rep] = end
        duration = max(end - warmup, 0.0)
        key = id_column or ("entity_id" if "entity_id" in data.columns else "")
        ids = data[key].tolist() if key else list(range(1, len(data) + 1))
        visits = pd.DataFrame(sim.visits, columns=["e", "s", "arrive", "start", "end", "leave"])
        visits["wait"] = visits["start"] - visits["arrive"]
        visits["service"] = visits["end"] - visits["start"]
        visits["blocked"] = visits["leave"] - visits["end"]
        counted = set(np.flatnonzero(times >= warmup).tolist())
        out = data.drop(columns=["entity_id"], errors="ignore")
        out.insert(0, "entity_id", ids)
        out.insert(0, "replication", rep)
        out["warmup"] = ~out.index.isin(counted)
        out["outcome"] = [sim.outcome.get(e, "unfinished") for e in range(len(out))]
        out["exit_time"] = [sim.exit_time.get(e, np.nan) for e in range(len(out))]
        out["time_in_system"] = out["exit_time"] - out[time_col]
        sums = visits.groupby("e")[["wait", "service", "blocked"]].sum(min_count=1)
        out["total_wait"] = sums["wait"].reindex(range(len(out))).fillna(0.0).to_numpy()
        out["total_service"] = sums["service"].reindex(range(len(out))).fillna(0.0).to_numpy()
        out["total_blocked"] = sums["blocked"].reindex(range(len(out))).fillna(0.0).to_numpy()
        for s, name in enumerate(names):
            per = visits[visits["s"] == s].groupby("e")["wait"].sum(min_count=1)
            out[f"wait_{name}"] = per.reindex(range(len(out))).to_numpy()
        ent_frames.append(out)
        v = visits.copy()
        v.insert(0, "station", [names[s] for s in v["s"]])
        v.insert(0, "entity_id", [ids[e] for e in v["e"]])
        v.insert(0, "replication", rep)
        visit_frames.append(v.drop(columns=["e", "s"]))
        for s, name in enumerate(names):
            mine = visits[(visits["s"] == s) & visits["e"].isin(counted)]
            started = mine[mine["start"].notna()]
            done = mine[mine["end"].notna()]
            lost_here = int(sum(1 for e in counted if sim.outcome.get(e, "") == f"lost at {name}"))
            servers_time = sim.area_servers[s]
            station_rows.append({
                "replication": rep, "station": name, "arrivals": len(mine), "served": int(len(done)), "lost": lost_here,
                "utilization": sim.area_serving[s] / servers_time if servers_time > 0 else np.nan,
                "blocked_share": sim.area_blocked[s] / servers_time if servers_time > 0 else np.nan,
                "avg_queue": sim.area_queue[s] / duration if duration > 0 else np.nan,
                "max_queue": sim.max_queue[s],
                "avg_wait": float(started["wait"].mean()) if len(started) else np.nan,
                "max_wait": float(started["wait"].max()) if len(started) else np.nan,
                "avg_service": float(done["service"].mean()) if len(done) else np.nan,
                "throughput": len(done) / duration if duration > 0 else np.nan,
            })
    entities = pd.concat(ent_frames, ignore_index=True)
    visits_all = pd.concat(visit_frames, ignore_index=True)
    stations_df = pd.DataFrame(station_rows)
    if log_full:
        warnings.warn(f"The event log stopped at {int(max_log):,} rows per replication. Raise the limit to keep more.")
    log = pd.DataFrame(logs, columns=["replication", "time", "event", "entity", "station", "queue_length", "busy_servers"])
    if len(log):
        label = {}
        for rep, frame in entities.groupby("replication"):
            label[rep] = frame["entity_id"].tolist()
        log["entity"] = [label[r][int(e)] if e is not None else np.nan for r, e in zip(log["replication"], log["entity"])]
    counted_rows = entities[~entities["warmup"]]
    per_rep = []
    for rep, frame in counted_rows.groupby("replication"):
        span = max(ends[rep] - warmup, 0.0)
        served = int((frame["outcome"] == "served").sum())
        lost = int(frame["outcome"].str.startswith("lost").sum())
        finished = frame[frame["outcome"] == "served"]
        per_rep.append({
            "replication": rep,
            "arrivals": ("system", float(len(frame))),
            "served": ("system", float(served)),
            "lost": ("system", float(lost)),
            "loss_rate": ("system", lost / len(frame) if len(frame) else np.nan),
            "avg_time_in_system": ("system", float(finished["time_in_system"].mean()) if served else np.nan),
            "max_time_in_system": ("system", float(finished["time_in_system"].max()) if served else np.nan),
            "avg_total_wait": ("system", float(finished["total_wait"].mean()) if served else np.nan),
            "throughput": ("system", served / span if span > 0 else np.nan),
        })
    metric_rows = []
    for rep_row in per_rep:
        for metric, pair in rep_row.items():
            if metric != "replication":
                metric_rows.append({"replication": rep_row["replication"], "metric": metric, "station": pair[0], "value": pair[1]})
    for _, r in stations_df.iterrows():
        for metric in ("utilization", "blocked_share", "avg_queue", "max_queue", "avg_wait", "max_wait", "served", "lost"):
            metric_rows.append({"replication": r["replication"], "metric": metric, "station": r["station"], "value": float(r[metric])})
    long = pd.DataFrame(metric_rows, columns=["replication", "metric", "station", "value"])
    summary_rows = []
    for (metric, where), frame in long.groupby(["metric", "station"], sort=False):
        values = frame["value"].dropna().to_numpy(dtype=float)
        n = len(values)
        mean = float(values.mean()) if n else np.nan
        sd = float(values.std(ddof=1)) if n > 1 else np.nan
        half = float(stats.t.ppf(0.975, n - 1) * sd / np.sqrt(n)) if n > 1 else np.nan
        summary_rows.append({"metric": metric, "station": where, "mean": mean, "sd": sd, "ci_low": mean - half if n > 1 else np.nan, "ci_high": mean + half if n > 1 else np.nan, "min": float(values.min()) if n else np.nan, "max": float(values.max()) if n else np.nan, "replications": n})
    summary = pd.DataFrame(summary_rows, columns=["metric", "station", "mean", "sd", "ci_low", "ci_high", "min", "max", "replications"])
    return entities, visits_all, stations_df, summary, log


def make_arrivals(gap, until, attributes=None, rates=None, seed=1):
    rng = np.random.default_rng(int(seed))
    frame = generate_arrivals(rng, gap, rates, float(until), attributes)
    frame.insert(0, "entity_id", range(1, len(frame) + 1))
    return frame
