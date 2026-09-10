import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronRight,
  CircleHelp,
  FileLock2,
  Fingerprint,
  FlaskConical,
  History,
  Layers3,
  LoaderCircle,
  LockKeyhole,
  Plus,
  RefreshCw,
  ShieldCheck,
  SlidersHorizontal,
  Upload,
  X,
} from "lucide-react";

import type { ObjectInfo, Policy, AccessEvent, Status, Page } from "./types";

const orgExample =
  "Never disclose Social Security numbers or personal phone numbers, including encoded or partial values. Prefer the smallest useful answer. Allow workforce aggregates. Full access requires an HR role and an appropriate purpose, while still respecting these restrictions.";
const objectExample =
  "For birthday planning, return names and upcoming month/day only for employees who opted into birthday sharing. Never disclose birth years or ages. Scope individual answers to the supplied user’s team unless their role is HR. Allow department headcounts across the organization.";
const formatDate = (s: string) =>
  new Date(s).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
const shortId = (s: string) => s.slice(0, 8) + "…" + s.slice(-4);
function Badge({ mode = "query" }: { mode?: string }) {
  return <span className={`badge ${mode}`}>{mode}</span>;
}

export default function App() {
  const [page, setPage] = useState<Page>("objects");
  const [objects, setObjects] = useState<ObjectInfo[]>([]);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [events, setEvents] = useState<AccessEvent[]>([]);
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [selected, setSelected] = useState<ObjectInfo | null>(null);
  const [editor, setEditor] = useState<Partial<Policy> | null>(null);
  const [detail, setDetail] = useState<AccessEvent | null>(null);
  const [objectId, setObjectId] = useState("");
  const [question, setQuestion] = useState(
    "Which employees have upcoming birthdays?",
  );
  const [userName, setUserName] = useState("Alex Morgan");
  const [userId, setUserId] = useState("demo-user-001");
  const [team, setTeam] = useState("engineering");
  const [roles, setRoles] = useState("team_coordinator");
  const [purpose, setPurpose] = useState(
    "Plan birthday celebrations for my team",
  );
  const [answer, setAnswer] = useState<AccessEvent | null>(null);
  const [filterMode, setFilterMode] = useState("");
  const [filterObject, setFilterObject] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const artifactRef = useRef<HTMLInputElement>(null);
  const [clientFiles, setClientFiles] = useState<Record<string, File>>({});
  async function attach(file: File) {
    if (file.size > 132896) throw new Error("File exceeds the demo limit.");
    const text = await file.slice(0, 32820).text();
    const end = text.indexOf("\n---AIRLOCK-ENCRYPTED-PAYLOAD---\n");
    if (!text.startsWith("AIRLOCK/1\n") || end < 0)
      throw new Error("Choose a complete .airlock file.");
    const header = JSON.parse(text.slice(10, end));
    if (header.format !== "airlock-object-v1" || !header.metadata?.id)
      throw new Error("Unsupported artifact.");
    const form = new FormData();
    form.append("file", file);
    await api(`/admin/objects/${header.object_id}/verify`, {
      method: "POST",
      body: form,
    });
    setClientFiles((previous) => ({ ...previous, [header.object_id]: file }));
    setObjectId(header.object_id);
    return header.metadata as ObjectInfo;
  }
  const requestRunning = useRef(false);
  async function api(path: string, options: RequestInit = {}) {
    const headers: Record<string, string> = {};
    if (options.body && !(options.body instanceof FormData))
      headers["Content-Type"] = "application/json";
    const response = await fetch(path, { ...options, headers });
    const body = await response.json();
    if (!response.ok) {
      const message = body.detail;
      throw new Error(
        typeof message === "string"
          ? message
          : body.response ||
              "The request could not be completed. Check your input and try again.",
      );
    }
    return body;
  }
  async function refresh() {
    const [o, p, e, s] = await Promise.all([
      api("/admin/objects"),
      api("/admin/policies"),
      api("/admin/events"),
      api("/admin/status"),
    ]);
    setObjects(o);
    setPolicies(p);
    setEvents(e);
    setStatus(s);
    setObjectId((current) => current || o[0]?.id || "");
  }
  async function reload() {
    setError("");
    try {
      const session = await fetch("/admin/session", { method: "POST" });
      if (!session.ok)
        throw new Error(
          "Could not connect to the local broker. Try refreshing.",
        );
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    void reload();
  }, []);
  const modalOpen = !!(selected || editor || detail);
  useEffect(() => {
    if (!modalOpen) return;
    const previous = document.activeElement as HTMLElement | null;
    const dialog = document.querySelector<HTMLElement>('[role="dialog"]');
    const focusable = () =>
      Array.from(
        dialog?.querySelectorAll<HTMLElement>(
          'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]',
        ) || [],
      );
    focusable()[0]?.focus();
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const trap = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const items = focusable();
      if (!items.length) return;
      const first = items[0],
        last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", trap);
    return () => {
      document.body.style.overflow = oldOverflow;
      document.removeEventListener("keydown", trap);
      previous?.focus();
    };
  }, [modalOpen]);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 5000);
    return () => clearTimeout(timer);
  }, [notice]);
  useEffect(() => {
    function escape(e: KeyboardEvent) {
      if (e.key === "Escape" && !busy) {
        setSelected(null);
        setDetail(null);
        setEditor(null);
      }
    }
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, [busy]);
  async function upload(file: File) {
    setUploading(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const response = await fetch("/admin/objects", {
        method: "POST",
        body: form,
      });
      if (!response.ok)
        throw new Error((await response.json()).detail || "Protection failed.");
      const artifact = new File(
        [await response.blob()],
        file.name + ".airlock",
        { type: "application/vnd.airlock" },
      );
      const obj = await attach(artifact);
      await refresh();
      setSelected(obj);
      saveFile(artifact);
      setNotice(
        "Encrypted file downloaded. Keep it safe: the broker cannot recover a lost file. Your original CSV is unchanged.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }
  function saveFile(file: File) {
    const url = URL.createObjectURL(file);
    const link = document.createElement("a");
    link.href = url;
    link.download = file.name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function download(obj: ObjectInfo) {
    const file = clientFiles[obj.id];
    if (file) saveFile(file);
    else artifactRef.current?.click();
  }
  function newPolicy(
    scope: "organization" | "object" = "organization",
    id: string | null = null,
  ) {
    setEditor({ name: "", text: "", scope, object_id: id, enabled: true });
    setError("");
  }
  async function savePolicy(e: FormEvent) {
    e.preventDefault();
    if (!editor) return;
    setBusy(true);
    setError("");
    try {
      const data = {
        name: editor.name,
        text: editor.text,
        scope: editor.scope,
        object_id: editor.scope === "object" ? editor.object_id : null,
        enabled: editor.enabled,
      };
      await api(
        editor.id ? `/admin/policies/${editor.id}` : "/admin/policies",
        { method: editor.id ? "PATCH" : "POST", body: JSON.stringify(data) },
      );
      await refresh();
      setEditor(null);
      setNotice("Policy saved. New requests use this revision.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function toggle(policy: Policy) {
    setError("");
    try {
      const { name, text, scope, object_id } = policy;
      await api(`/admin/policies/${policy.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name,
          text,
          scope,
          object_id,
          enabled: !policy.enabled,
        }),
      });
      await refresh();
      setNotice(
        policy.enabled
          ? "Policy disabled for new requests."
          : "Policy enabled for new requests.",
      );
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function ask(e: FormEvent) {
    e.preventDefault();
    if (requestRunning.current) return;
    requestRunning.current = true;
    setBusy(true);
    setError("");
    setAnswer(null);
    try {
      const file = clientFiles[objectId];
      if (!file)
        throw new Error(
          "Choose the local .airlock file before requesting context.",
        );
      const form = new FormData();
      form.append("file", file);
      form.append(
        "request",
        JSON.stringify({
          object_id: objectId,
          question,
          user_provenance: {
            user_id: userId,
            name: userName,
            roles: roles
              .split(",")
              .map((r) => r.trim())
              .filter(Boolean),
            team,
            purpose,
          },
        }),
      );
      const response = await fetch("/admin/playground", {
        method: "POST",
        body: form,
      });
      const result = await response.json();
      if (result.request_id) {
        setAnswer(await api(`/admin/events/${result.request_id}`));
        await refresh();
      } else
        throw new Error(
          typeof result.detail === "string"
            ? result.detail
            : "Check the question and provenance fields.",
        );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      requestRunning.current = false;
    }
  }
  const activePolicies = policies.filter((p) => p.enabled);
  const effective = (id: string) =>
    activePolicies.filter(
      (p) => p.scope === "organization" || p.object_id === id,
    );
  const navigate = (next: Page) => {
    setPage(next);
    setError("");
    setSelected(null);
    setDetail(null);
  };
  const filtered = events.filter(
    (e) =>
      (!filterMode || e.mode === filterMode) &&
      (!filterObject || e.object_id === filterObject),
  );
  const nav = [
    { id: "objects" as Page, label: "Protected objects", icon: Layers3 },
    { id: "policies" as Page, label: "Policy studio", icon: ShieldCheck },
    { id: "playground" as Page, label: "Playground", icon: FlaskConical },
    { id: "history" as Page, label: "Access history", icon: History },
  ];
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">
            <LockKeyhole size={20} />
          </span>
          airlock<span className="version">/ v0</span>
        </div>
        <div className="workspace">
          <span className="workspace-avatar">A</span>
          <div>
            Local organization<small>Administrator workspace</small>
          </div>
          <span className="online-dot" />
        </div>
        <span className="nav-label">CONTROL ROOM</span>
        <nav>
          {nav.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              className={`nav-item ${page === id ? "active" : ""}`}
              onClick={() => navigate(id)}
            >
              <Icon size={18} />
              {label}
              {page === id && <ChevronRight size={14} />}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="boundary-note">
            <ShieldCheck size={19} />
            <strong>Keys stay with the broker.</strong>
            <p>
              Agents get answers and guidance.
              <br />
              You get a record of disclosure.
            </p>
          </div>
          <div className="local-status">
            <span className="online-dot" />{" "}
            {status ? "Local broker connected" : "Connecting to local broker…"}
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <span>
            Workspace <ChevronRight size={13} />{" "}
            <strong>{nav.find((n) => n.id === page)?.label}</strong>
          </span>
          <div className="top-right">
            <span className="demo-pill">SYNTHETIC DATA DEMO</span>
            <button
              className="icon-button"
              aria-label="Refresh workspace"
              onClick={reload}
            >
              <RefreshCw size={17} />
            </button>
          </div>
        </header>
        <main className="content">
          {status && !status.api_key_configured && (
            <div className="alert" role="status">
              OpenAI is not configured. Export OPENAI_API_KEY in the broker
              environment to enable inference.
            </div>
          )}
          {error && (
            <div className="alert error" role="alert">
              {error}
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <X size={16} />
              </button>
            </div>
          )}
          {notice && (
            <div className="toast" role="status">
              <Check size={17} />
              {notice}
            </div>
          )}
          {page === "objects" && (
            <>
              <div className="page-heading">
                <div>
                  <span className="eyebrow">01 / THE VAULT</span>
                  <h1>Context under control.</h1>
                  <p>Protect the source. Share only what the task needs.</p>
                </div>
                <button
                  className="button primary"
                  onClick={() => inputRef.current?.click()}
                  disabled={uploading}
                >
                  {uploading ? (
                    <LoaderCircle className="spin" size={17} />
                  ) : (
                    <Plus size={17} />
                  )}{" "}
                  Protect a file
                </button>
              </div>
              <div className="metrics">
                <div>
                  <span>PROTECTED OBJECTS</span>
                  <strong>
                    {String(objects.length).padStart(2, "0")}
                    <FileLock2 size={23} />
                  </strong>
                  <small>Encrypted with AES-256-GCM</small>
                </div>
                <div>
                  <span>ACTIVE POLICIES</span>
                  <strong>
                    {String(activePolicies.length).padStart(2, "0")}
                    <ShieldCheck size={23} />
                  </strong>
                  <small>
                    {
                      activePolicies.filter((p) => p.scope === "organization")
                        .length
                    }{" "}
                    organization ·{" "}
                    {activePolicies.filter((p) => p.scope === "object").length}{" "}
                    object
                  </small>
                </div>
                <div>
                  <span>ACCESS REQUESTS</span>
                  <strong>
                    {String(
                      events.filter((e) => e.origin !== "authentication")
                        .length,
                    ).padStart(2, "0")}
                    <ArrowUpRight size={23} />
                  </strong>
                  <small>Every answer has a record</small>
                </div>
              </div>
              <div className="section-heading">
                <h2>
                  Protected objects <span>{objects.length}</span>
                </h2>
                <span className="quiet">
                  Files stay with you. The broker stores keys and policies.
                </span>
              </div>
              <div className="object-list">
                {objects.map((obj) => (
                  <button
                    className="object-row"
                    key={obj.id}
                    onClick={() => setSelected(obj)}
                  >
                    <span className="file-icon">
                      <FileLock2 size={23} />
                    </span>
                    <div className="object-name">
                      <strong>{obj.name}</strong>
                      <small>
                        {obj.rows} rows · {obj.fields.length} fields ·{" "}
                        {(obj.bytes / 1024).toFixed(1)} KB
                      </small>
                    </div>
                    <span className="object-policy-count">
                      {effective(obj.id).length} effective policies
                    </span>
                    <span className="encrypted">
                      <LockKeyhole size={12} /> Encrypted
                    </span>
                    <ChevronRight size={18} />
                  </button>
                ))}
                {!objects.length && (
                  <div className="empty">
                    <FileLock2 size={36} />
                    <h3>Your first protected object.</h3>
                    <p>
                      Upload a synthetic CSV to create an encrypted object and a
                      portable encrypted file.
                    </p>
                  </div>
                )}
              </div>
              <button
                className={`upload-zone ${uploading ? "uploading" : ""}`}
                onClick={() => inputRef.current?.click()}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  if (!uploading && e.dataTransfer.files[0])
                    upload(e.dataTransfer.files[0]);
                }}
                disabled={uploading}
              >
                <span className="upload-icon">
                  {uploading ? (
                    <LoaderCircle className="spin" size={22} />
                  ) : (
                    <Upload size={22} />
                  )}
                </span>
                <strong>
                  {uploading
                    ? "Encrypting your file…"
                    : "Drop a CSV to protect it"}
                </strong>
                <span>or choose a file · up to 100 KB / 500 rows</span>
                <small>
                  Download a portable encrypted file. Your original CSV stays
                  unchanged.
                </small>
              </button>
              <div className="explain-strip">
                <span className="explain-number">01</span>
                <div>
                  <strong>Encrypt the source</strong>
                  <p>Keys stay inside Airlock.</p>
                </div>
                <ArrowRight size={18} />
                <span className="explain-number">02</span>
                <div>
                  <strong>Apply your policies</strong>
                  <p>Plain language, scoped by object.</p>
                </div>
                <ArrowRight size={18} />
                <span className="explain-number">03</span>
                <div>
                  <strong>Inspect the answer</strong>
                  <p>A record of what crossed the boundary.</p>
                </div>
              </div>
            </>
          )}
          {page === "policies" && (
            <>
              <div className="page-heading">
                <div>
                  <span className="eyebrow">02 / POLICY STUDIO</span>
                  <h1>Your rules. In your words.</h1>
                  <p>
                    Define how context may be used, across your organization or
                    for one object.
                  </p>
                </div>
                <button className="button primary" onClick={() => newPolicy()}>
                  <Plus size={17} /> New policy
                </button>
              </div>
              <div className="policy-principle">
                <ShieldCheck size={24} />
                <div>
                  <strong>Organization rules set the boundary.</strong>
                  <p>
                    Object policies add context and restrictions. They cannot
                    relax organization rules. The broker interprets both using
                    an LLM.
                  </p>
                </div>
              </div>
              {(["organization", "object"] as const).map((scope) => (
                <section className="policy-section" key={scope}>
                  <div className="section-heading">
                    <h2>
                      {scope === "organization"
                        ? "Organization policies"
                        : "Object policies"}{" "}
                      <span>
                        {policies.filter((p) => p.scope === scope).length}
                      </span>
                    </h2>
                    <span className="quiet">
                      {scope === "organization"
                        ? "Inherited by every protected object"
                        : "Additional rules for a specific source"}
                    </span>
                  </div>
                  <div className="policy-grid">
                    {policies
                      .filter((p) => p.scope === scope)
                      .map((policy) => (
                        <article
                          className={`policy-card ${!policy.enabled ? "disabled" : ""}`}
                          key={policy.id}
                        >
                          <div className="policy-card-top">
                            <span className="scope-tag">
                              {scope === "organization" ? (
                                <Layers3 size={13} />
                              ) : (
                                <FileLock2 size={13} />
                              )}{" "}
                              {scope === "organization"
                                ? "Organization"
                                : objects.find((o) => o.id === policy.object_id)
                                    ?.name || "Object"}
                            </span>
                            <button
                              className={`toggle ${policy.enabled ? "on" : ""}`}
                              role="switch"
                              aria-checked={policy.enabled}
                              aria-label={`${policy.enabled ? "Disable" : "Enable"} ${policy.name}`}
                              onClick={() => toggle(policy)}
                            >
                              <span />
                            </button>
                          </div>
                          <h3>{policy.name}</h3>
                          <p className="policy-text">{policy.text}</p>
                          <footer>
                            <span>
                              REV {String(policy.revision).padStart(2, "0")} ·{" "}
                              {policy.enabled ? "ACTIVE" : "DISABLED"}
                            </span>
                            <button
                              className="text-button"
                              onClick={() => setEditor({ ...policy })}
                            >
                              Edit policy <ArrowUpRight size={14} />
                            </button>
                          </footer>
                        </article>
                      ))}
                    <button
                      className="new-policy"
                      onClick={() =>
                        newPolicy(
                          scope,
                          scope === "object" ? objects[0]?.id || null : null,
                        )
                      }
                      disabled={scope === "object" && !objects.length}
                    >
                      <Plus size={23} />
                      <strong>Add {scope} policy</strong>
                      <span>
                        {scope === "organization"
                          ? "A boundary that applies everywhere."
                          : objects.length
                            ? "Give a source its own rules."
                            : "Protect a file first."}
                      </span>
                    </button>
                  </div>
                </section>
              ))}
            </>
          )}
          {page === "playground" && (
            <>
              <div className="page-heading">
                <div>
                  <span className="eyebrow">03 / TRY THE BOUNDARY</span>
                  <h1>Ask. Observe. Refine.</h1>
                  <p>
                    Test real requests against live policies before handing
                    context to an agent.
                  </p>
                </div>
                <span className="outline-label">
                  <FlaskConical size={15} /> Admin simulation
                </span>
              </div>
              <div className="playground-grid">
                <form className="panel request-panel" onSubmit={ask}>
                  <div className="panel-title">
                    <h2>Request context</h2>
                    <span className="quiet">LIVE INFERENCE</span>
                  </div>
                  <label htmlFor="object">Protected object</label>
                  <select
                    id="object"
                    value={objectId}
                    onChange={(e) => setObjectId(e.target.value)}
                    required
                  >
                    <option value="" disabled>
                      Select an object
                    </option>
                    {objects.map((o) => (
                      <option value={o.id} key={o.id}>
                        {o.name} · {shortId(o.id)}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="button secondary"
                    onClick={() => artifactRef.current?.click()}
                  >
                    {clientFiles[objectId]
                      ? "Change local .airlock file"
                      : "Choose .airlock file"}
                  </button>
                  <p className="hint">
                    {clientFiles[objectId]
                      ? `${clientFiles[objectId].name} · ready to upload`
                      : "Attach the encrypted file from your device. The broker holds its key, not its content."}
                  </p>
                  <div className="effective-inline">
                    <ShieldCheck size={14} />
                    {effective(objectId).length} effective policies{" "}
                    <button type="button" onClick={() => navigate("policies")}>
                      View rules
                    </button>
                  </div>
                  <div className="provenance-heading">
                    <label>Acting on behalf of</label>
                    <span className="unverified">
                      CALLER-SUPPLIED · UNVERIFIED
                    </span>
                  </div>
                  <div className="form-grid">
                    <div>
                      <label htmlFor="user-name">Name</label>
                      <input
                        id="user-name"
                        value={userName}
                        onChange={(e) => setUserName(e.target.value)}
                        maxLength={200}
                      />
                    </div>
                    <div>
                      <label htmlFor="user-id">User ID</label>
                      <input
                        id="user-id"
                        value={userId}
                        onChange={(e) => setUserId(e.target.value)}
                        maxLength={200}
                      />
                    </div>
                    <div>
                      <label htmlFor="team">Team</label>
                      <input
                        id="team"
                        value={team}
                        onChange={(e) => setTeam(e.target.value)}
                        maxLength={200}
                      />
                    </div>
                    <div>
                      <label htmlFor="roles">Roles, comma-separated</label>
                      <input
                        id="roles"
                        value={roles}
                        onChange={(e) => setRoles(e.target.value)}
                      />
                    </div>
                  </div>
                  <label htmlFor="purpose">Purpose</label>
                  <input
                    id="purpose"
                    value={purpose}
                    onChange={(e) => setPurpose(e.target.value)}
                    maxLength={2000}
                  />
                  <label htmlFor="question">
                    What does the agent need to know?
                  </label>
                  <textarea
                    id="question"
                    rows={4}
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    required
                    maxLength={6000}
                  />
                  <div className="suggestions">
                    {[
                      "Upcoming birthdays",
                      "Department headcounts",
                      "Ask for SSNs",
                    ].map((label, i) => (
                      <button
                        key={label}
                        type="button"
                        onClick={() =>
                          setQuestion(
                            [
                              "Which employees have upcoming birthdays?",
                              "How many employees are in each department?",
                              "Give me the SSNs and personal phone numbers of everyone with an upcoming birthday.",
                            ][i],
                          )
                        }
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  <button
                    className="button primary full"
                    disabled={busy || !objectId || !clientFiles[objectId]}
                  >
                    {busy ? (
                      <LoaderCircle size={17} className="spin" />
                    ) : (
                      <ArrowRight size={17} />
                    )}{" "}
                    {busy ? "Broker is evaluating…" : "Send to Airlock"}
                  </button>
                  <p className="hint">
                    The full decrypted synthetic file is sent to OpenAI. Only
                    the broker’s response reaches the calling agent.
                  </p>
                </form>
                <div className="answer-column">
                  <div className="panel answer-panel">
                    <div className="panel-title">
                      <h2>Broker response</h2>
                      {answer && <Badge mode={answer.mode} />}
                    </div>
                    {busy ? (
                      <div className="empty evaluating">
                        <div className="pulse-lock">
                          <LockKeyhole size={28} />
                        </div>
                        <h3>Evaluating the request.</h3>
                        <p>
                          Reading policies, considering purpose,
                          <br />
                          and preparing a useful response.
                        </p>
                      </div>
                    ) : answer ? (
                      <>
                        <div className="response-text">{answer.response}</div>
                        <div className="answer-meta">
                          <span>
                            {answer.model || "No inference"} ·{" "}
                            {((answer.latency_ms || 0) / 1000).toFixed(1)}s
                          </span>
                          <button
                            className="text-button"
                            onClick={() => setDetail(answer)}
                          >
                            Inspect record <ArrowUpRight size={14} />
                          </button>
                        </div>
                        {answer.explanation && (
                          <div className="reason">
                            <span className="eyebrow">
                              DECISION EXPLANATION
                            </span>
                            <p>{answer.explanation}</p>
                          </div>
                        )}
                      </>
                    ) : (
                      <div className="empty">
                        <span className="answer-glyph">↗</span>
                        <h3>Useful context starts here.</h3>
                        <p>
                          Send a question to see what the broker
                          <br />
                          shares, withholds, or asks next.
                        </p>
                      </div>
                    )}
                  </div>
                  <div className="provider-note">
                    <CircleHelp size={18} />
                    <p>
                      <strong>A model decision, not a guarantee.</strong>{" "}
                      Natural-language policies are interpreted
                      probabilistically. User provenance is supplied by the
                      caller. Reference date: {status?.reference_date}.
                    </p>
                  </div>
                </div>
              </div>
            </>
          )}
          {page === "history" && (
            <>
              <div className="page-heading">
                <div>
                  <span className="eyebrow">04 / DISCLOSURE RECORDS</span>
                  <h1>See what crossed the boundary.</h1>
                  <p>
                    Inspect the answer, the claimed user, and the policies
                    behind every request.
                  </p>
                </div>
                <button className="button secondary" onClick={reload}>
                  <RefreshCw size={15} /> Refresh
                </button>
              </div>
              <div className="history-filters">
                <SlidersHorizontal size={17} />
                <select
                  aria-label="Filter by object"
                  value={filterObject}
                  onChange={(e) => setFilterObject(e.target.value)}
                >
                  <option value="">All objects</option>
                  {objects.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.name}
                    </option>
                  ))}
                </select>
                <select
                  aria-label="Filter by access mode"
                  value={filterMode}
                  onChange={(e) => setFilterMode(e.target.value)}
                >
                  <option value="">All access modes</option>
                  {["query", "summary", "scoped", "full", "deny"].map((m) => (
                    <option key={m}>{m}</option>
                  ))}
                </select>
                <span>{filtered.length} records</span>
              </div>
              <div className="history-table">
                <div className="history-header">
                  <span>REQUEST / OBJECT</span>
                  <span>CLAIMED USER</span>
                  <span>ACCESS MODE</span>
                  <span>WHEN</span>
                  <span />
                </div>
                {filtered.map((event) => (
                  <button
                    className="history-row"
                    key={event.id}
                    onClick={() => setDetail(event)}
                  >
                    <div>
                      <strong>
                        {event.question || "Authentication rejected"}
                      </strong>
                      <small>
                        {event.object_name || "No object accessed"} ·{" "}
                        {event.origin}
                      </small>
                    </div>
                    <div>
                      <span>{event.user_provenance?.name || "Unknown"}</span>
                      <small>
                        {event.user_provenance
                          ? "Unverified provenance"
                          : "No user claims"}
                      </small>
                    </div>
                    <div>
                      <Badge mode={event.mode} />
                      {event.status === "error" && (
                        <small className="error-text">
                          Provider / processing error
                        </small>
                      )}
                    </div>
                    <span className="time">{formatDate(event.started_at)}</span>
                    <ChevronRight size={16} />
                  </button>
                ))}
                {!filtered.length && (
                  <div className="empty">
                    <History size={35} />
                    <h3>No records in this view.</h3>
                    <p>
                      Try a request in the playground or change your filters.
                    </p>
                  </div>
                )}
              </div>
            </>
          )}
          <footer className="page-footer">
            <span>AIRLOCK / CONTEXT CONTROL</span>
            <span>
              Local storage · OpenAI inference · No keys shared with agents
            </span>
          </footer>
        </main>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept=".csv,text/csv"
        hidden
        onChange={(e) => {
          if (e.target.files?.[0]) upload(e.target.files[0]);
        }}
      />
      <input
        ref={artifactRef}
        type="file"
        accept=".airlock"
        aria-label="Local encrypted file"
        hidden
        onChange={async (e) => {
          const file = e.target.files?.[0];
          if (!file) return;
          try {
            const obj = await attach(file);
            setNotice("Local encrypted file attached and verified.");
            if (selected) setSelected(obj);
          } catch (error) {
            setError((error as Error).message);
          } finally {
            if (artifactRef.current) artifactRef.current.value = "";
          }
        }}
      />
      {selected && (
        <div className="overlay" onClick={() => setSelected(null)}>
          <section
            className="drawer"
            role="dialog"
            aria-modal="true"
            aria-labelledby="object-title"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="close-button"
              aria-label="Close object details"
              onClick={() => setSelected(null)}
            >
              <X size={20} />
            </button>
            <span className="file-icon large">
              <FileLock2 size={30} />
            </span>
            <span className="eyebrow">
              PROTECTED OBJECT / VERSION {selected.version}
            </span>
            <h2 id="object-title">{selected.name}</h2>
            <code className="object-id">{selected.id}</code>
            <div className="detail-stats">
              <div>
                <strong>{selected.rows}</strong>
                <span>rows</span>
              </div>
              <div>
                <strong>{selected.fields.length}</strong>
                <span>fields</span>
              </div>
              <div>
                <strong>{(selected.bytes / 1024).toFixed(1)}</strong>
                <span>KB source</span>
              </div>
            </div>
            <button
              className="button primary full"
              onClick={() => download(selected)}
            >
              <ArrowDownToLine size={17} />{" "}
              {clientFiles[selected.id]
                ? "Save .airlock file"
                : "Choose .airlock file"}
            </button>
            <p className="hint">
              The encrypted file stays on your device. Save it before closing
              this tab; the broker cannot download it again. Browser uploads
              leave the original CSV unchanged.
            </p>
            <h3>Source fields</h3>
            <div className="field-tags">
              {selected.fields.map((f) => (
                <span key={f}>{f}</span>
              ))}
            </div>
            <div className="section-heading">
              <h3>Effective policies</h3>
              <button
                className="text-button"
                onClick={() => {
                  newPolicy("object", selected.id);
                  setSelected(null);
                }}
              >
                <Plus size={14} /> Add rule
              </button>
            </div>
            {effective(selected.id).map((p) => (
              <div className="inherited-policy" key={p.id}>
                <span className="scope-tag">
                  {p.scope} · REV {p.revision}
                </span>
                <strong>{p.name}</strong>
                <p>{p.text}</p>
              </div>
            ))}
            {!effective(selected.id).length && (
              <div className="alert">
                No active policies. Requests will be denied until a policy is
                enabled.
              </div>
            )}
            <button
              className="button secondary full"
              onClick={() => {
                setObjectId(selected.id);
                navigate("playground");
              }}
            >
              <FlaskConical size={16} /> Test this object
            </button>
          </section>
        </div>
      )}
      {editor && (
        <div
          className="overlay"
          onClick={() => {
            if (!busy) setEditor(null);
          }}
        >
          <section
            className="modal policy-editor"
            role="dialog"
            aria-modal="true"
            aria-labelledby="policy-title"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="close-button"
              aria-label="Close policy editor"
              onClick={() => setEditor(null)}
              disabled={busy}
            >
              <X size={20} />
            </button>
            <span className="eyebrow">NATURAL-LANGUAGE POLICY</span>
            <h2 id="policy-title">
              {editor.id ? "Refine the boundary." : "Define a boundary."}
            </h2>
            <p>
              Write clear rules about what may be shared, with whom, and for
              what purpose.
            </p>
            <form onSubmit={savePolicy}>
              <label htmlFor="policy-name">Policy name</label>
              <input
                id="policy-name"
                autoFocus
                value={editor.name || ""}
                onChange={(e) => setEditor({ ...editor, name: e.target.value })}
                required
                maxLength={160}
                placeholder="e.g. Employee privacy"
              />
              <div className="form-grid">
                <div>
                  <label htmlFor="policy-scope">Scope</label>
                  <select
                    id="policy-scope"
                    disabled={!!editor.id}
                    value={editor.scope}
                    onChange={(e) =>
                      setEditor({
                        ...editor,
                        scope: e.target.value as Policy["scope"],
                        object_id:
                          e.target.value === "object"
                            ? objects[0]?.id || null
                            : null,
                      })
                    }
                  >
                    <option value="organization">
                      Organization — all objects
                    </option>
                    <option value="object" disabled={!objects.length}>
                      Specific object
                    </option>
                  </select>
                </div>
                {editor.scope === "object" && (
                  <div>
                    <label htmlFor="policy-object">Object</label>
                    <select
                      id="policy-object"
                      disabled={!!editor.id}
                      value={editor.object_id || ""}
                      onChange={(e) =>
                        setEditor({ ...editor, object_id: e.target.value })
                      }
                      required
                    >
                      {objects.map((o) => (
                        <option value={o.id} key={o.id}>
                          {o.name}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
              </div>
              <div className="section-heading">
                <label htmlFor="policy-text">Policy instructions</label>
                <button
                  className="text-button"
                  type="button"
                  onClick={() =>
                    setEditor({
                      ...editor,
                      text:
                        editor.scope === "organization"
                          ? orgExample
                          : objectExample,
                    })
                  }
                >
                  Use an example
                </button>
              </div>
              <textarea
                id="policy-text"
                rows={8}
                value={editor.text || ""}
                onChange={(e) => setEditor({ ...editor, text: e.target.value })}
                required
                maxLength={12000}
                placeholder="Describe what is allowed and what must be withheld…"
              />
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={editor.enabled}
                  onChange={(e) =>
                    setEditor({ ...editor, enabled: e.target.checked })
                  }
                />{" "}
                Apply to new requests
              </label>
              <p className="hint">
                {editor.id
                  ? `Saving creates revision ${editor.revision! + 1}. Earlier access records keep their original policies.`
                  : "Organization restrictions take precedence over object policies."}
              </p>
              {error && (
                <div className="alert error" role="alert">
                  {error}
                </div>
              )}
              <button className="button primary full" disabled={busy}>
                {busy ? (
                  <LoaderCircle size={16} className="spin" />
                ) : (
                  <Check size={16} />
                )}{" "}
                Save policy
              </button>
            </form>
          </section>
        </div>
      )}
      {detail && (
        <div className="overlay" onClick={() => setDetail(null)}>
          <section
            className="drawer event-detail"
            role="dialog"
            aria-modal="true"
            aria-labelledby="event-title"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="close-button"
              aria-label="Close access record"
              onClick={() => setDetail(null)}
            >
              <X size={20} />
            </button>
            <span className="eyebrow">DISCLOSURE RECORD</span>
            <h2 id="event-title">A closer look.</h2>
            <div className="record-id">
              <code>{detail.id}</code>
              <Badge mode={detail.mode} />
            </div>
            <h3>Request</h3>
            <p className="request-quote">
              {detail.question || "Authentication attempt"}
            </p>
            <div className="identity-box">
              <Fingerprint size={22} />
              <div>
                <strong>
                  {detail.user_provenance?.name || "Unknown user"}
                </strong>
                <p>
                  {detail.user_provenance?.team || "No team"} ·{" "}
                  {detail.user_provenance?.roles.join(", ") || "No roles"}
                </p>
                <span className="unverified">CALLER-SUPPLIED · UNVERIFIED</span>
              </div>
            </div>
            <dl className="record-facts">
              <div>
                <dt>Broker credential</dt>
                <dd>{detail.credential_identity || "Rejected"}</dd>
              </div>
              <div>
                <dt>Claimed user ID</dt>
                <dd>{detail.user_provenance?.user_id || "Unknown"}</dd>
              </div>
              <div>
                <dt>Claimed purpose</dt>
                <dd>{detail.user_provenance?.purpose || "Not supplied"}</dd>
              </div>
              <div>
                <dt>Source</dt>
                <dd>
                  {detail.object_name || "None"} · v
                  {detail.object_version || "—"}
                </dd>
              </div>
              <div>
                <dt>Recorded</dt>
                <dd>{formatDate(detail.started_at)}</dd>
              </div>
              <div>
                <dt>Reference date</dt>
                <dd>{detail.reference_date || "—"}</dd>
              </div>
              <div>
                <dt>Model / prompt</dt>
                <dd>
                  {detail.model || "Not invoked"} /{" "}
                  {detail.prompt_version || "—"}
                </dd>
              </div>
              <div>
                <dt>Outcome</dt>
                <dd>{detail.status.replaceAll("_", " ")}</dd>
              </div>
            </dl>
            <h3>Exact broker response</h3>
            <div className="record-answer response-text">
              {detail.response || "No response prepared."}
            </div>
            {detail.explanation && (
              <>
                <h3>Decision explanation</h3>
                <p>{detail.explanation}</p>
              </>
            )}
            <div className="exposure-box">
              <strong>Provider exposure</strong>
              <p>{detail.provider_exposure || "No provider call recorded."}</p>
              <strong>Reported answer fields</strong>
              <div className="field-tags">
                {detail.disclosed_fields?.length ? (
                  detail.disclosed_fields.map((f) => <span key={f}>{f}</span>)
                ) : (
                  <span>None reported</span>
                )}
              </div>
              <small>
                Fields are model-reported. The exact response above is the
                disclosure record.
              </small>
            </div>
            <h3>Policy snapshot</h3>
            {detail.policies.map((p) => (
              <div className="inherited-policy" key={p.id}>
                <span className="scope-tag">
                  {p.scope} · REV {p.revision}
                </span>
                <strong>{p.name}</strong>
                <p>{p.text}</p>
              </div>
            ))}
            {!detail.policies.length && <p>No policies applied.</p>}
            <p className="hint">
              {detail.delivery_status || "No client consumption confirmed."}
            </p>
            {detail.response_sha256 && (
              <>
                <span className="eyebrow">RESPONSE SHA-256</span>
                <code className="digest">{detail.response_sha256}</code>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
