import React, {
  useState,
  useEffect,
  createContext,
  useContext,
  useCallback,
} from "react";
import { createRoot } from "react-dom/client";
import {
  BrowserRouter,
  Routes,
  Route,
  NavLink,
  Link,
  Navigate,
  useParams,
  useNavigate,
} from "react-router-dom";
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronRight,
  Clock,
  Code2,
  Cpu,
  Download,
  FlaskConical,
  Layers,
  LayoutDashboard,
  LogOut,
  Menu,
  Pause,
  Play,
  Plus,
  Search,
  Server,
  Settings2,
  ShieldCheck,
  Users,
  X,
  Upload,
  ExternalLink,
  Copy,
} from "lucide-react";
import { api, User, Run, active, date, duration } from "./api";
import MotionViewer from "./MotionViewer";
import RobotIllustration from "./RobotIllustration";
import "./style.css";

const ENV_OPTIONS = [1024, 2048, 4096];
const REPO = "https://github.com/IntelligentRoboticsLab/booster_mjlab";
const Auth = createContext<{ user: User | null; reload: () => Promise<void> }>({
  user: null,
  reload: async () => {},
});
const Notice = createContext<(s: string) => void>(() => {});
function usePoll<T>(
  fn: () => Promise<T>,
  deps: unknown[] = [],
  interval = 3000,
) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    const update = async () => {
      try {
        const result = await fn();
        if (alive) {
          setData(result);
          setError("");
        }
      } catch (e) {
        if (alive) setError((e as Error).message);
      }
    };
    update();
    const timer = setInterval(update, interval);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, deps);
  return { data, error };
}
function useAction() {
  const notify = useContext(Notice);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const run = async (fn: () => Promise<unknown>, message = "Saved") => {
    setBusy(true);
    setError("");
    try {
      await fn();
      if (message) notify(message);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, run };
}
function ErrorBox({ error }: { error?: string }) {
  return error ? (
    <div className="error" role="alert">
      {error}
    </div>
  ) : null;
}
function Button({
  children,
  onClick,
  variant = "",
  disabled = false,
  type = "button",
}: {
  children: React.ReactNode;
  onClick?: () => void;
  variant?: string;
  disabled?: boolean;
  type?: "button" | "submit";
}) {
  return (
    <button
      type={type}
      className={"button " + variant}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}
function Head({
  title,
  text,
  action,
}: {
  title: string;
  text?: string;
  action?: React.ReactNode;
}) {
  return (
    <header className="page-head">
      <div>
        <h1>{title}</h1>
        {text && <p>{text}</p>}
      </div>
      {action}
    </header>
  );
}
function Badge({ status }: { status: string }) {
  return (
    <span className={"badge " + status.toLowerCase()}>
      <i />
      {status.toLowerCase()}
    </span>
  );
}
function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="stat">
      <div className="stat-top">{label}</div>
      <strong>{value}</strong>
    </div>
  );
}
function Empty({ children }: { children: React.ReactNode }) {
  return <div className="empty">{children}</div>;
}
function Field({
  label,
  value,
  onChange,
  type = "number",
  min = 0,
  max = 1000000,
}: {
  label: string;
  value: any;
  onChange: (v: any) => void;
  type?: string;
  min?: number;
  max?: number;
}) {
  return (
    <label>
      {label}
      <input
        type={type}
        value={value ?? ""}
        min={min}
        max={max}
        step="any"
        onChange={(e) =>
          onChange(type === "number" ? Number(e.target.value) : e.target.value)
        }
      />
    </label>
  );
}
function Toggle({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="toggle-row">
      <span>{label}</span>
      <input
        type="checkbox"
        checked={value}
        onChange={(e) => onChange(e.target.checked)}
      />
    </label>
  );
}

function Login() {
  const { user, reload } = useContext(Auth);
  const nav = useNavigate(),
    action = useAction();
  const [email, setEmail] = useState(""),
    [password, setPassword] = useState(""),
    [message, setMessage] = useState("");
  const { data: health } = usePoll<any>(() => api("/health"), [], 30000);
  useEffect(() => {
    const consume = () => {
      const token = new URLSearchParams(location.hash.slice(1)).get("token");
      if (!token) return;
      history.replaceState(null, "", "/login");
      action.run(async () => {
        await api("/auth/verify", "POST", { token });
        const account = await api<User>("/me");
        await reload();
        nav(account.role === "admin" ? "/admin" : "/dashboard");
      }, "");
    };
    consume();
    window.addEventListener("hashchange", consume);
    return () => window.removeEventListener("hashchange", consume);
  }, []);
  if (user)
    return <Navigate to={user.role === "admin" ? "/admin" : "/dashboard"} />;
  return (
    <div className="auth-page">
      <div className="auth-art">
        <div className="brand">
          <span className="brand-mark">
            <Cpu />
          </span>
          Robot Training Hub
        </div>
        <div className="auth-copy">
          <span className="pill">BOOSTER K1 WORKSHOP</span>
          <h1>
            Train motion tracking
            <br />
            with mjlab.
          </h1>
          <p>
            Upload a motion, choose your training settings, and follow the run
            from your browser.
          </p>
          <RobotIllustration />
          <div className="auth-steps">
            <span>01 &nbsp; Upload a K1 motion CSV</span>
            <span>02 &nbsp; Preview the motion</span>
            <span>03 &nbsp; Train and review TensorBoard</span>
          </div>
          <a href={REPO} target="_blank" rel="noreferrer" className="text-link">
            Training repository <ArrowUpRight size={15} />
          </a>
        </div>
      </div>
      <div className="auth-form">
        <div className="eyebrow">ROBOT TRAINING HUB</div>
        <h1>Sign in</h1>
        <p>Use the account your workshop administrator approved.</p>
        {health?.demo_login && (
          <div className="demo-login">
            <b>Local development</b>
            {["admin", "participant"].map((role) => (
              <Button
                key={role}
                variant={role === "participant" ? "secondary" : ""}
                disabled={action.busy}
                onClick={() =>
                  action.run(async () => {
                    const result = await api("/auth/demo", "POST", { role });
                    await reload();
                    nav(result.redirect);
                  }, "")
                }
              >
                Open {role} demo
              </Button>
            ))}
          </div>
        )}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            action.run(async () => {
              const result = await api("/auth/password", "POST", {
                email,
                password,
              });
              await reload();
              nav(result.redirect);
            }, "");
          }}
        >
          <label>
            Email
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="username"
            />
          </label>
          <label>
            Password
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </label>
          <Button type="submit" disabled={action.busy}>
            {action.busy ? "Signing in…" : "Sign in"}
            <ArrowRight size={16} />
          </Button>
        </form>
        <ErrorBox error={action.error} />
        <p className="auth-switch">
          Use the email and password sent by your workshop administrator.
        </p>
        <button
          className="text-link"
          disabled={!email || action.busy}
          onClick={() =>
            action.run(async () => {
              const r = await api("/auth/request", "POST", { email });
              setMessage(r.message);
            }, "")
          }
        >
          Email me a sign-in link
        </button>
        {message && <div className="info">{message}</div>}
        <div className="auth-note">
          <ShieldCheck size={18} />
          Registration is managed by the workshop administrator.
        </div>
      </div>
    </div>
  );
}

function Shell() {
  const { user, reload } = useContext(Auth);
  const [mobile, setMobile] = useState(false);
  if (!user) return <Navigate to="/login" />;
  return (
    <div className="app">
      <button
        className="mobile-menu"
        aria-label="Open navigation"
        onClick={() => setMobile(!mobile)}
      >
        <Menu />
      </button>
      <aside className={"sidebar " + (mobile ? "open" : "")}>
        <Link
          className="brand"
          to={user.role === "admin" ? "/admin" : "/dashboard"}
        >
          <span className="brand-mark">
            <Cpu size={23} />
          </span>
          <span>
            Robot Training<span className="brand-second">Hub</span>
          </span>
        </Link>
        <div className="workspace">
          <FlaskConical size={18} />
          <div>
            Booster K1 workshop<small>mjlab motion tracking</small>
          </div>
        </div>
        <nav onClick={() => setMobile(false)}>
          <NavLink to="/dashboard">
            <LayoutDashboard />
            Dashboard
          </NavLink>
          <NavLink to="/motions">
            <Play />
            Motions
          </NavLink>
          <NavLink to="/train/new">
            <Plus />
            New training
          </NavLink>
          <NavLink to="/policies">
            <Download />
            Policies
          </NavLink>
          <NavLink to="/runs" end>
            <Activity />
            My runs
          </NavLink>
          <a href={REPO} target="_blank" rel="noreferrer">
            <Code2 />
            Training repository <ArrowUpRight size={12} />
          </a>
        </nav>
        {user.role === "admin" && (
          <>
            <div className="nav-label admin-label">ADMIN</div>
            <nav onClick={() => setMobile(false)}>
              <NavLink to="/admin" end>
                <ShieldCheck />
                Overview
              </NavLink>
              <NavLink to="/admin/runs">
                <Layers />
                All runs
              </NavLink>
              <NavLink to="/admin/servers">
                <Server />
                Compute
              </NavLink>
              <NavLink to="/admin/users">
                <Users />
                Participants
              </NavLink>
              <NavLink to="/admin/settings">
                <Settings2 />
                Settings
              </NavLink>
            </nav>
          </>
        )}
        <div className="sidebar-bottom">
          <div className="profile">
            <span className="avatar">
              {user.email.slice(0, 2).toUpperCase()}
            </span>
            <div>
              <b title={user.email}>{user.email}</b>
              <small>{user.role}</small>
            </div>
            <button
              title="Sign out"
              onClick={async () => {
                await api("/auth/logout", "POST");
                await reload();
              }}
            >
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      <main className="main">
        <div className="topbar">
          <div>
            Workshop <ChevronRight size={12} />
            <b>Booster K1</b>
          </div>
          <span className="role-pill">
            <ShieldCheck size={14} />
            {user.role === "admin" ? "Administrator" : "Participant"}
          </span>
        </div>
        <div className="content">
          <Routes>
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/motions" element={<Motions />} />
            <Route path="/train/new" element={<NewTraining />} />
            <Route path="/runs" element={<Runs />} />
            <Route path="/policies" element={<Policies />} />
            <Route path="/runs/:id" element={<RunPage />} />
            <Route path="/runs/:id/code" element={<Repository />} />
            <Route path="/code" element={<Repository />} />
            <Route
              path="/admin/*"
              element={
                user.role === "admin" ? (
                  <AdminRoutes />
                ) : (
                  <Navigate to="/dashboard" />
                )
              }
            />
            <Route
              path="*"
              element={
                <Navigate
                  to={user.role === "admin" ? "/admin" : "/dashboard"}
                />
              }
            />
          </Routes>
          <footer className="footer">
            <span>ROBOT TRAINING HUB</span>
            <span>Booster K1 · mjlab</span>
          </footer>
        </div>
      </main>
    </div>
  );
}

function WorkshopHero({ admin = false }: { admin?: boolean }) {
  return (
    <section className="workshop-hero">
      <div className="workshop-hero-copy">
        <span className="hero-kicker">
          <span /> BOOSTER K1 · MOTION TRACKING
        </span>
        <h2>
          {admin ? (
            <>
              A little coordination.
              <br />A lot of possibility.
            </>
          ) : (
            <>
              Your motion.
              <br />
              Your next breakthrough.
            </>
          )}
        </h2>
        <p>
          {admin
            ? "Keep the workshop moving. Manage access, watch compute capacity, and follow every experiment in one place."
            : "Bring a motion to life. Preview a K1 reference, start training, and follow your robot’s progress."}
        </p>
        <div className="actions">
          <Link
            className="button hero-primary"
            to={admin ? "/admin/users" : "/train/new"}
          >
            {admin ? "Manage participants" : "Start an experiment"}
            <ArrowUpRight size={17} />
          </Link>
          <Link
            className="hero-secondary"
            to={admin ? "/admin/servers" : "/motions"}
          >
            {admin ? "View compute" : "Explore motions"}
            <ArrowRight size={16} />
          </Link>
        </div>
      </div>
      <div className="workshop-hero-art">
        <RobotIllustration compact />
        <div className="hero-model-label">
          <span />
          Booster K1 <small>22 degrees of freedom</small>
        </div>
      </div>
    </section>
  );
}

function Dashboard() {
  const { user } = useContext(Auth);
  const { data: runs, error } = usePoll<Run[]>(() => api("/runs"));
  const { data: options } = usePoll<any>(() => api("/options"), [], 15000);
  const own = (runs || []).filter((r) => r.email === user?.email),
    current = own.find(active);
  return (
    <>
      <Head
        title="Training dashboard"
        text="Upload a motion, start a run, and review the results."
        action={
          <Link className="button" to="/train/new">
            <Plus size={16} />
            New training
          </Link>
        }
      />
      <ErrorBox error={error} />
      <WorkshopHero />
      <div className="stats">
        <Stat label="Your runs" value={own.length} />
        <Stat
          label="Maximum environments"
          value={(
            options?.user_env_limit ??
            options?.max_envs ??
            2048
          ).toLocaleString()}
        />
        <Stat
          label="Active run"
          value={current ? current.status.toLowerCase() : "None"}
        />
      </div>
      {current && (
        <section className="panel details">
          <div className="section-title">
            <h2>{current.name}</h2>
            <Badge status={current.status} />
          </div>
          <p>
            {current.queue_position
              ? `Queue position ${current.queue_position}`
              : `${current.iteration} / ${current.spec.iterations} iterations · ${current.server_name || "Assigning compute"}`}
          </p>
          <Link to={"/runs/" + current.id} className="button secondary">
            Open run <ArrowRight size={16} />
          </Link>
        </section>
      )}
      <div className="two-col">
        <Link to="/motions" className="resource-card">
          <span className="resource-icon">
            <Upload />
          </span>
          <div>
            <h3>Upload and preview a motion</h3>
            <p>
              Use a Booster K1 CSV with root pose and 22 joint angles. Preview
              it before training.
            </p>
          </div>
        </Link>
        <a
          href={REPO}
          target="_blank"
          rel="noreferrer"
          className="resource-card"
        >
          <span className="resource-icon">
            <Code2 />
          </span>
          <div>
            <h3>Training repository</h3>
            <p>
              Robot configuration, rewards, and the mjlab training pipeline.
            </p>
            <b>
              Open GitHub <ArrowUpRight size={14} />
            </b>
          </div>
        </a>
      </div>
      <section className="panel" style={{ marginTop: 24 }}>
        <div className="section-title">
          <h2>Recent runs</h2>
          <Link to="/runs" className="text-link">
            All runs <ArrowRight size={14} />
          </Link>
        </div>
        <RunTable runs={own.slice(0, 6)} />
      </section>
    </>
  );
}
function RunTable({ runs, admin = false }: { runs: Run[]; admin?: boolean }) {
  const action = useAction();
  const [stopping, setStopping] = useState<Run>();
  if (!runs.length)
    return (
      <Empty>
        No training runs yet.{" "}
        <Link to="/train/new" className="text-link">
          Start a run
        </Link>
      </Empty>
    );
  return (
    <>
      <ErrorBox error={action.error} />
      <div className="table-scroll">
        <table className="run-table">
          <thead>
            <tr>
              <th>Experiment</th>
              {admin && <th>Participant</th>}
              <th>Status</th>
              <th>Motion / environments</th>
              <th>Server</th>
              <th>Progress</th>
              <th>Elapsed</th>
              <th className="run-actions">Actions</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.id}>
                <td>
                  <Link className="run-name" to={"/runs/" + r.id}>
                    {r.name}
                  </Link>
                  <small>{r.id.slice(0, 8)}</small>
                </td>
                {admin && <td>{r.email}</td>}
                <td>
                  <Badge status={r.status} />
                  {!!r.cancel && active(r) && <small>Stopping requested</small>}
                </td>
                <td>
                  {r.spec.motion.label}
                  <small>{r.spec.num_envs.toLocaleString()} environments</small>
                </td>
                <td>{r.server_name || "Queued"}</td>
                <td>
                  <div className="mini-progress">
                    {r.iteration} / {r.spec.iterations}
                    <progress value={r.iteration} max={r.spec.iterations} />
                  </div>
                </td>
                <td>{duration(r)}</td>
                <td className="run-actions">
                  <div className="actions">
                    {admin && active(r) && (
                      <Button
                        variant="danger small"
                        disabled={action.busy || r.cancel}
                        onClick={() => setStopping(r)}
                      >
                        {r.cancel
                          ? "Stopping…"
                          : r.status === "QUEUED"
                            ? "Remove queued"
                            : "Stop"}
                      </Button>
                    )}
                    <Link to={"/runs/" + r.id} aria-label={"Open " + r.name}>
                      <ArrowUpRight size={16} />
                    </Link>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {stopping && (
        <div className="modal-backdrop">
          <section className="modal compact">
            <div className="section-title">
              <h2>
                {stopping.status === "QUEUED"
                  ? "Remove queued run"
                  : "Stop training"}
              </h2>
              <button
                onClick={() => setStopping(undefined)}
                aria-label="Close stop dialog"
              >
                <X />
              </button>
            </div>
            <div className="modal-content">
              <p>
                <strong>{stopping.name}</strong>
              </p>
              <p>
                {stopping.email} ·{" "}
                {stopping.server_name || "Waiting for compute"}
              </p>
              <p>
                This stops this workshop run. Its saved artifacts remain
                available.
              </p>
              <ErrorBox error={action.error} />
            </div>
            <div className="modal-footer">
              <Button
                variant="secondary"
                onClick={() => setStopping(undefined)}
              >
                Keep running
              </Button>
              <Button
                variant="danger"
                disabled={action.busy}
                onClick={() =>
                  action.run(async () => {
                    await api("/runs/" + stopping.id + "/cancel", "POST");
                    setStopping(undefined);
                  }, "Stop requested")
                }
              >
                Confirm stop
              </Button>
            </div>
          </section>
        </div>
      )}
    </>
  );
}
function Runs({ admin = false }: { admin?: boolean }) {
  const [q, setQ] = useState(""),
    [status, setStatus] = useState("");
  const { data, error } = usePoll<Run[]>(
    () =>
      api("/runs?" + new URLSearchParams({ q, ...(status ? { status } : {}) })),
    [q, status],
  );
  return (
    <>
      <Head
        title={admin ? "All training runs" : "My training runs"}
        text={
          admin
            ? "Inspect progress, stop jobs, or update queue priority."
            : "Your queued, running, and completed experiments."
        }
      />
      <ErrorBox error={error} />
      <section className="panel">
        <div className="filterbar">
          <div className="search">
            <Search size={16} />
            <input
              aria-label="Search runs"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search name, ID, or email"
            />
          </div>
          <select
            aria-label="Run status"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="">All statuses</option>
            {[
              "QUEUED",
              "STARTING",
              "RUNNING",
              "COMPLETED",
              "FAILED",
              "CANCELED",
            ].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </div>
        {data && <RunTable runs={data} admin={admin} />}
      </section>
    </>
  );
}

function Motions() {
  const { user } = useContext(Auth);
  const { data: motions, error } = usePoll<any[]>(() => api("/motions"));
  const [file, setFile] = useState<File>(),
    [label, setLabel] = useState(""),
    [fps, setFps] = useState(50),
    [selected, setSelected] = useState("");
  const action = useAction();
  useEffect(() => {
    if (motions?.length && !selected) setSelected(motions[0].id);
  }, [motions]);
  const motion = motions?.find((m) => m.id === selected);
  return (
    <>
      <Head
        title="Motion library"
        text="Upload a Booster K1 CSV and preview it in the browser."
      />
      <ErrorBox error={error || action.error} />
      <form
        className="panel details upload-form"
        onSubmit={(e) => {
          e.preventDefault();
          action.run(async () => {
            if (!file) throw Error("Choose a CSV file");
            const query = new URLSearchParams({
              label: label || file.name.replace(/\.csv$/i, ""),
              fps: String(fps),
              shared: String(user?.role === "admin"),
            });
            const response = await fetch("/api/motions?" + query, {
              method: "POST",
              headers: { "X-Hub-Request": "1", "Content-Type": "text/csv" },
              body: file,
            });
            const result = await response.json();
            if (!response.ok) throw Error(result.detail || "Upload failed");
            setSelected(result.id);
            setFile(undefined);
            setLabel("");
          }, "Motion uploaded");
        }}
      >
        <div className="form-grid three">
          <label>
            Motion name
            <input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. MJ dance"
              maxLength={120}
            />
          </label>
          <label>
            CSV file
            <input
              type="file"
              accept=".csv,text/csv"
              required
              onChange={(e) => setFile(e.target.files?.[0])}
            />
          </label>
          <Field
            label="Frame rate (Hz)"
            value={fps}
            min={1}
            max={240}
            onChange={setFps}
          />
        </div>
        <p>
          Expected: root XYZ in meters, quaternion XYZW, and 22 K1 joint
          positions in radians. Booster Assets motion files use 50 Hz.
        </p>
        <Button type="submit" disabled={action.busy}>
          <Upload size={16} />
          {action.busy ? "Validating…" : "Upload CSV"}
        </Button>
      </form>
      <div className="motion-layout">
        <section className="panel motion-library">
          {motions?.map((m) => (
            <button
              key={m.id}
              className={
                m.id === selected ? "motion-item selected" : "motion-item"
              }
              onClick={() => setSelected(m.id)}
            >
              <b>{m.label}</b>
              <small>
                {m.frames.toLocaleString()} frames · {m.duration.toFixed(1)} s ·{" "}
                {m.fps} Hz
              </small>
              <span className="badge">
                {m.approved ? "Approved" : "Awaiting approval"}
              </span>
            </button>
          ))}
          {!motions?.length && (
            <Empty>Upload a motion to preview it here.</Empty>
          )}
        </section>
        <div>
          {motion && (
            <>
              <div className="section-title outside">
                <div>
                  <h2>{motion.label}</h2>
                  <p>Booster K1 reference motion</p>
                </div>
                <div className="actions">
                  <a
                    className="button secondary"
                    href={"/api/motions/" + motion.id + "/download"}
                  >
                    <Download size={15} />
                    CSV
                  </a>
                  {motion.approved ? (
                    <Link
                      className="button"
                      to={"/train/new?motion=" + motion.id}
                    >
                      Train this motion <ArrowRight size={15} />
                    </Link>
                  ) : (
                    user?.role === "admin" && (
                      <Button
                        onClick={() =>
                          action.run(
                            () =>
                              api(
                                "/admin/motions/" + motion.id + "/approve",
                                "POST",
                                { approved: true, shared: true },
                              ),
                            "Motion approved",
                          )
                        }
                      >
                        Approve motion
                      </Button>
                    )
                  )}
                </div>
              </div>
              <MotionViewer key={motion.id} motionId={motion.id} />
            </>
          )}
        </div>
      </div>
    </>
  );
}

function NewTraining() {
  const { data: o, error } = usePoll<any>(() => api("/options"), [], 15000);
  const nav = useNavigate(),
    action = useAction();
  const [name, setName] = useState(""),
    [motion, setMotion] = useState(
      new URLSearchParams(location.search).get("motion") || "",
    ),
    [envs, setEnvs] = useState(2048),
    [iterations, setIterations] = useState(1000),
    [policyInterval, setPolicyInterval] = useState(50);
  useEffect(() => {
    if (o) {
      const available = o.presets.filter(
        (n: number) =>
          n <= Math.min(o.max_envs, o.user_env_limit ?? o.max_envs),
      );
      setEnvs(
        available.includes(o.default_envs)
          ? o.default_envs
          : (available[0] ?? 0),
      );
      if (!motion) setMotion(o.motions[0]?.id || "");
    }
  }, [!!o]);
  return (
    <>
      <Head
        title="New training"
        text="Choose an approved motion and training size. Compute is assigned automatically."
      />
      <ErrorBox error={error || action.error} />
      {o && (
        <form
          className="training-layout"
          onSubmit={(e) => {
            e.preventDefault();
            action.run(async () => {
              const r = await api("/runs", "POST", {
                name,
                motion_id: motion,
                num_envs: envs,
                iterations,
                policy_interval: policyInterval,
              });
              nav("/runs/" + r.id);
            }, "Training queued");
          }}
        >
          <section className="panel details">
            <h2>Training settings</h2>
            <label>
              Experiment name
              <input
                required
                value={name}
                maxLength={80}
                onChange={(e) => setName(e.target.value)}
                placeholder="MJ tracking – first run"
              />
            </label>
            <label>
              Motion
              <select
                required
                value={motion}
                onChange={(e) => setMotion(e.target.value)}
              >
                <option value="" disabled>
                  Select a motion
                </option>
                {o.motions.map((m: any) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
              </select>
            </label>
            {!o.motions.length && (
              <p>
                No approved motions yet. <Link to="/motions">Upload a CSV</Link>{" "}
                or ask the administrator.
              </p>
            )}
            <label>
              Parallel environments
              <div
                className="environment-options"
                role="group"
                aria-label="Parallel environments"
              >
                {o.presets
                  .filter(
                    (n: number) =>
                      n <= Math.min(o.max_envs, o.user_env_limit ?? o.max_envs),
                  )
                  .map((n: number) => (
                    <button
                      type="button"
                      className={
                        envs === n
                          ? "environment-option selected"
                          : "environment-option"
                      }
                      key={n}
                      onClick={() => setEnvs(n)}
                      aria-pressed={envs === n}
                    >
                      <span>{n.toLocaleString()}</span>
                      <small>
                        {n === 1024
                          ? "Light"
                          : n === 2048
                            ? "Balanced"
                            : "Large"}
                      </small>
                      {envs === n && <Check size={14} />}
                    </button>
                  ))}
              </div>
              <small>
                Your maximum:{" "}
                {Math.min(
                  o.max_envs,
                  o.user_env_limit ?? o.max_envs,
                ).toLocaleString()}{" "}
                environments.
              </small>
            </label>
            <Field
              label="Training iterations"
              value={iterations}
              min={1}
              max={o.max_iterations}
              onChange={setIterations}
            />
            <label>
              Policy export interval
              <select
                value={policyInterval}
                onChange={(e) => setPolicyInterval(Number(e.target.value))}
              >
                {[50, 100, 200].map((n) => (
                  <option key={n} value={n}>
                    Every {n} learning iterations
                  </option>
                ))}
              </select>
              <small>
                The latest 10 policy versions are retained. Initial and final
                saves are included.
              </small>
            </label>
            <div className="form-submit">
              <span>One outstanding run per participant.</span>
              <Button type="submit" disabled={action.busy || !motion || !envs}>
                {action.busy ? "Preparing run…" : "Start training"}
                <ArrowRight size={16} />
              </Button>
            </div>
          </section>
          <aside className="training-aside">
            <section className="panel details">
              <h3>Booster K1 tracking</h3>
              <p>
                The same pinned mjlab tracking task runs on each worker. CSV
                motions are converted to the required tracking format before
                training.
              </p>
              <p>
                Watch reward and loss curves in TensorBoard. Download your
                checkpoint when the run finishes.
              </p>
              <a
                href={REPO}
                target="_blank"
                rel="noreferrer"
                className="text-link"
              >
                Training repository <ArrowUpRight size={14} />
              </a>
            </section>
          </aside>
        </form>
      )}
    </>
  );
}

function RewardChart({ metrics = [] }: { metrics: any[] | undefined }) {
  const data = metrics.filter((m) => Number.isFinite(m.reward));
  if (data.length < 2)
    return (
      <Empty>Reward metrics will appear after the first iterations.</Empty>
    );
  const min = Math.min(...data.map((m) => m.reward)),
    max = Math.max(...data.map((m) => m.reward));
  const points = data.map(
    (v, i) =>
      `${40 + (i * 620) / (data.length - 1)},${190 - ((v.reward - min) / (max - min || 1)) * 160}`,
  );
  return (
    <svg
      className="chart"
      viewBox="0 0 700 220"
      role="img"
      aria-label="Reward over training iterations"
    >
      <line x1="40" y1="190" x2="660" y2="190" stroke="#e9e6f2" />
      <polyline
        points={points.join(" ")}
        fill="none"
        stroke="#9273d2"
        strokeWidth="2.5"
      />
      <text x="5" y="30">
        {max.toFixed(2)}
      </text>
      <text x="5" y="190">
        {min.toFixed(2)}
      </text>
      <text x="40" y="215">
        Iteration {data[0].step}
      </text>
      <text x="600" y="215">
        {data.at(-1).step}
      </text>
    </svg>
  );
}
function RunPage() {
  const { id } = useParams();
  const { user } = useContext(Auth),
    action = useAction();
  const { data: r, error } = usePoll<any>(() => api("/runs/" + id), [id]);
  const { data: logs } = usePoll<any>(() => api("/runs/" + id + "/logs"), [id]);
  const [tab, setTab] = useState("progress"),
    [priority, setPriority] = useState(0);
  if (!r)
    return (
      <>
        <ErrorBox error={error} />
        <p>Loading run…</p>
      </>
    );
  return (
    <>
      <Head
        title={r.name}
        text={r.spec.motion.label + " · Booster K1 tracking"}
        action={
          <div className="actions">
            <a
              className="button secondary"
              href={REPO}
              target="_blank"
              rel="noreferrer"
            >
              <Code2 size={16} />
              Repository
            </a>
            {active(r) && (
              <Button
                variant="danger"
                disabled={action.busy || r.cancel}
                onClick={() =>
                  action.run(
                    () => api("/runs/" + id + "/cancel", "POST"),
                    "Stop requested",
                  )
                }
              >
                {r.cancel ? "Stopping…" : "Stop training"}
                <X size={16} />
              </Button>
            )}
            {user?.role === "admin" && r.status === "FAILED" && (
              <Button
                onClick={() =>
                  action.run(
                    () => api("/admin/runs/" + id + "/retry", "POST"),
                    "Retry queued",
                  )
                }
              >
                Retry
              </Button>
            )}
          </div>
        }
      />
      <ErrorBox error={error || action.error || r.error} />
      {r.execution?.mock && (
        <div className="warning">This is an archived simulated run.</div>
      )}
      {r.worker_online === false && active(r) && (
        <div className="warning">
          Worker disconnected. This run will not be retried automatically.
        </div>
      )}
      <div className="run-status panel">
        <div>
          <Badge status={r.status} />
          <span>
            {r.queue_position
              ? `Queue position ${r.queue_position}`
              : r.server_name || "Waiting for compute"}
          </span>
        </div>
        <span>
          {r.email} · {date(r.created)}
        </span>
      </div>
      <div className="stats four">
        <Stat
          label="Iterations"
          value={`${r.iteration} / ${r.spec.iterations}`}
        />
        <Stat label="Environments" value={r.spec.num_envs.toLocaleString()} />
        <Stat label="Elapsed" value={duration(r)} />
        <Stat
          label="GPU memory"
          value={r.gpu_mb ? `${(r.gpu_mb / 1024).toFixed(1)} GiB` : "—"}
        />
      </div>
      <div className="tabs">
        {["progress", "logs", "results"].map((t) => (
          <button
            key={t}
            className={tab === t ? "selected" : ""}
            onClick={() => setTab(t)}
          >
            {t[0].toUpperCase() + t.slice(1)}
          </button>
        ))}
        <a
          href={"/api/runs/" + id + "/tensorboard/"}
          target="_blank"
          rel="noreferrer"
        >
          Open TensorBoard <ExternalLink size={14} />
        </a>
      </div>
      {tab === "progress" && (
        <>
          <section className="panel">
            <div className="section-title">
              <h2>Mean reward</h2>
              <a
                href={"/api/runs/" + id + "/tensorboard/"}
                target="_blank"
                rel="noreferrer"
                className="button secondary"
              >
                TensorBoard <ExternalLink size={15} />
              </a>
            </div>
            <RewardChart metrics={r.metrics} />
            <div className="chart-footer">
              Training progress
              <progress value={r.iteration} max={r.spec.iterations} />
            </div>
          </section>
          <section className="panel details">
            <h3>Run details</h3>
            <dl>
              <dt>Motion</dt>
              <dd>{r.spec.motion.label}</dd>
              <dt>GPU</dt>
              <dd>{r.gpu || "Pending"}</dd>
              <dt>Seed</dt>
              <dd>{r.spec.seed}</dd>
              <dt>Tracking task</dt>
              <dd>{r.spec.task}</dd>
              <dt>Metrics</dt>
              <dd>
                {r.tensorboard_available
                  ? "Available in TensorBoard"
                  : "Waiting for the first training metrics"}
              </dd>
            </dl>
          </section>
          {user?.role === "admin" && r.status === "QUEUED" && (
            <section className="panel details">
              <h3>Queue priority</h3>
              <div className="inline-form">
                <input
                  aria-label="Priority"
                  type="number"
                  value={priority}
                  min={-100}
                  max={100}
                  onChange={(e) => setPriority(Number(e.target.value))}
                />
                <Button
                  onClick={() =>
                    action.run(() =>
                      api("/admin/runs/" + id + "/priority", "POST", {
                        priority,
                      }),
                    )
                  }
                >
                  Set priority
                </Button>
              </div>
            </section>
          )}
        </>
      )}
      {tab === "logs" && (
        <section className="panel">
          <div className="section-title">
            <h2>Training log</h2>
            <a
              className="button secondary"
              href={"/api/runs/" + id + "/logs/download"}
            >
              <Download size={15} />
              Download
            </a>
          </div>
          <pre className="terminal">
            {logs?.text || "Waiting for worker output…"}
          </pre>
        </section>
      )}
      {tab === "results" && (
        <section className="panel">
          <div className="section-title">
            <h2>Policies, checkpoints and run files</h2>
            <Link className="button secondary" to="/policies">
              Open policy list
            </Link>
          </div>
          <p className="details">
            ONNX files are exported inference policies. PT files are training
            checkpoints. Configuration files record how the run was trained.
          </p>
          {r.artifacts?.length ? (
            <div className="artifact-list">
              {r.artifacts.map((a: any) => (
                <a
                  key={a.path}
                  href={
                    "/api/runs/" +
                    id +
                    "/artifacts?path=" +
                    encodeURIComponent(a.path)
                  }
                >
                  <Download size={17} />
                  <div>
                    <b>{a.path}</b>
                    <small>{(a.size / 1024).toFixed(1)} KiB</small>
                  </div>
                </a>
              ))}
            </div>
          ) : (
            <Empty>
              Policies, checkpoints and configuration files are uploaded when
              training finishes. ONNX export warnings appear in the training
              log.
            </Empty>
          )}
        </section>
      )}
    </>
  );
}

function Policies() {
  const { data, error } = usePoll<any[]>(() => api("/policies"));
  const [search, setSearch] = useState("");
  const { user } = useContext(Auth);
  return (
    <>
      <Head
        title="Policies"
        text="Versioned ONNX exports from your training runs. New runs export every 50 learning iterations by default and retain the latest 10 versions."
      />
      <ErrorBox error={error} />
      <section className="panel details">
        <label>
          Find policy
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search experiment, motion or participant"
          />
        </label>
        <div className="export-format-grid">
          <div>
            <h3>ONNX · inference model</h3>
            <p>
              For a compatible simulator or robot runtime. Includes the tracking
              motion reference.
            </p>
          </div>
          <div>
            <h3>PT · training checkpoint</h3>
            <p>
              Weights and training state for resuming mjlab training. Available
              when this checkpoint is retained.
            </p>
          </div>
          <div>
            <h3>ZIP · policy bundle</h3>
            <p>
              ONNX, resolved YAML configuration, commit IDs and a hash manifest
              for sharing and deployment setup.
            </p>
          </div>
        </div>
      </section>
      {!data?.length ? (
        <Empty>
          Policies appear here after mjlab produces its first ONNX export.
          Existing runs keep their original save interval.
        </Empty>
      ) : (
        <section className="panel">
          <div className="table-scroll">
            <table className="policy-table">
              <colgroup>
                {(user?.role === "admin"
                  ? [23, 21, 12, 12, 8, 24]
                  : [30, 15, 15, 10, 30]
                ).map((width, index) => (
                  <col key={index} style={{ width: width + "%" }} />
                ))}
              </colgroup>
              <thead>
                <tr>
                  <th>Experiment / motion</th>
                  {user?.role === "admin" && <th>Participant</th>}
                  <th>Checkpoint</th>
                  <th>Run status</th>
                  <th>Size</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data
                  .filter((p) =>
                    `${p.name} ${p.motion} ${p.email}`
                      .toLowerCase()
                      .includes(search.toLowerCase()),
                  )
                  .map((p) => (
                    <tr key={p.job_id + p.path}>
                      <td>
                        <Link to={"/runs/" + p.job_id}>{p.name}</Link>
                        <small>{p.motion}</small>
                      </td>
                      {user?.role === "admin" && <td>{p.email}</td>}
                      <td>
                        {p.iteration_index === null
                          ? "Latest"
                          : `Index ${p.iteration_index}`}
                        <small>{p.server_name}</small>
                      </td>
                      <td>
                        <Badge status={p.status} />
                      </td>
                      <td>{(p.size / 1048576).toFixed(1)} MiB</td>
                      <td>
                        <div className="actions">
                          <a
                            className="button small"
                            href={
                              "/api/runs/" +
                              p.job_id +
                              "/policies/export?path=" +
                              encodeURIComponent(p.path)
                            }
                          >
                            <Download size={15} />
                            Export policy ZIP
                          </a>
                          <a
                            className="button secondary small"
                            href={
                              "/api/runs/" +
                              p.job_id +
                              "/artifacts?path=" +
                              encodeURIComponent(p.path)
                            }
                          >
                            ONNX
                          </a>
                          {p.checkpoint_path && (
                            <a
                              className="button secondary small"
                              href={
                                "/api/runs/" +
                                p.job_id +
                                "/artifacts?path=" +
                                encodeURIComponent(p.checkpoint_path)
                              }
                            >
                              PT checkpoint
                            </a>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}

function Repository() {
  return (
    <>
      <Head
        title="Training repository"
        text="Booster K1 robot configuration, rewards, and mjlab training code."
      />
      <section className="panel details">
        <a className="button" href={REPO} target="_blank" rel="noreferrer">
          Open training repository <ExternalLink size={16} />
        </a>
      </section>
    </>
  );
}
function AdminRoutes() {
  return (
    <Routes>
      <Route index element={<AdminOverview />} />
      <Route path="runs" element={<Runs admin />} />
      <Route path="servers" element={<Servers />} />
      <Route path="users" element={<Participants />} />
      <Route path="settings" element={<WorkshopSettings />} />
    </Routes>
  );
}
function AdminOverview() {
  const { data: o, error } = usePoll<any>(() => api("/admin/overview"));
  const { data: servers } = usePoll<any[]>(() => api("/admin/servers"));
  const { data: runs } = usePoll<Run[]>(() => api("/runs"));
  const action = useAction();
  return (
    <>
      <Head
        title="Workshop overview"
        text="Manage participants, compute, and the training queue."
        action={
          o && (
            <Button
              variant="secondary"
              onClick={() =>
                action.run(
                  () =>
                    api("/admin/settings", "PUT", {
                      ...o.settings,
                      paused: !o.settings.paused,
                    }),
                  o.settings.paused
                    ? "Scheduling resumed"
                    : "Scheduling paused",
                )
              }
            >
              {o.settings.paused ? <Play size={16} /> : <Pause size={16} />}{" "}
              {o.settings.paused ? "Resume queue" : "Pause queue"}
            </Button>
          )
        }
      />
      <ErrorBox error={error || action.error} />
      {o?.settings.paused && (
        <div className="warning">
          Scheduling is paused. Running jobs continue.
        </div>
      )}
      <WorkshopHero admin />
      <div className="stats four">
        <Stat label="Participants" value={o?.participants ?? 0} />
        <Stat
          label="Running / starting"
          value={(o?.jobs.RUNNING || 0) + (o?.jobs.STARTING || 0)}
        />
        <Stat label="Queued" value={o?.jobs.QUEUED || 0} />
        <Stat
          label="Concurrent job limit"
          value={o?.settings.max_running_jobs ?? 10}
        />
      </div>
      <div className="fleet-heading">
        <div>
          <span className="eyebrow">WORKSHOP INFRASTRUCTURE</span>
          <h2>Compute fleet</h2>
        </div>
        <span className="coordinator-tag">
          <Server size={13} />
          Coordinator · {o?.coordinator_host || "Connecting"}
        </span>
      </div>
      <div className="server-grid">
        {servers?.map((s) => (
          <ServerCard key={s.id} server={s} />
        ))}
      </div>
      <section className="panel">
        <div className="section-title">
          <h2>Recent runs</h2>
          <Link to="/admin/runs" className="text-link">
            All runs <ArrowRight size={15} />
          </Link>
        </div>
        {runs && <RunTable runs={runs.slice(0, 8)} admin />}
      </section>
    </>
  );
}
function ServerCard({
  server: s,
  onEdit,
}: {
  server: any;
  onEdit?: () => void;
}) {
  return (
    <section className="server-card">
      <div className="server-card-head">
        <Server size={19} />
        <h3>{s.name}</h3>
        <Badge
          status={
            s.quarantined ? "QUARANTINED" : s.online ? "ONLINE" : "OFFLINE"
          }
        />
      </div>
      {s.inventory.gpus?.map((g: any) => (
        <div className="gpu" key={g.uuid}>
          <div className="gpu-label">
            <b>{g.name}</b>
            <span>{g.utilization}% utilization</span>
          </div>
          <progress value={g.total_mb - g.free_mb} max={g.total_mb} />
          <div className="gpu-memory">
            <span>
              {((g.total_mb - g.free_mb) / 1024).toFixed(1)} /{" "}
              {(g.total_mb / 1024).toFixed(1)} GiB
            </span>
            <span>{s.config.reserve_mb / 1024} GiB reserved</span>
          </div>
        </div>
      ))}
      {!s.inventory.gpus?.length && (
        <div className="gpu muted">Waiting for worker heartbeat</div>
      )}
      <div className="server-info">
        <span>
          {s.active_jobs} active · max {s.config.max_jobs} per GPU
        </span>
        <span>
          MPS{" "}
          {s.inventory.mps?.ready
            ? "ready"
            : s.config.mps_enabled
              ? "unavailable"
              : "off"}
        </span>
      </div>
      {s.capacity?.map((capacity: any) => (
        <p className="server-capacity" key={capacity.gpu}>
          {capacity.additional_jobs} more{" "}
          {capacity.additional_jobs === 1 ? "job" : "jobs"} at{" "}
          {capacity.num_envs.toLocaleString()} environments ·{" "}
          {capacity.memory_percent}% memory ceiling
        </p>
      ))}
      {s.inventory.mock && <div className="mock-label">SIMULATED WORKER</div>}
      <div className="server-card-foot">
        <span>{s.config.enabled ? "Enabled" : "Disabled"}</span>
        {onEdit && (
          <button onClick={onEdit}>
            Configure <Settings2 size={14} />
          </button>
        )}
      </div>
    </section>
  );
}
function Servers() {
  const { data: servers, error } = usePoll<any[]>(() => api("/admin/servers"));
  const [editing, setEditing] = useState<any>(),
    [config, setConfig] = useState<any>(),
    [confirmed, setConfirmed] = useState(false);
  const action = useAction();
  const update = (key: string, v: any) => setConfig({ ...config, [key]: v });
  return (
    <>
      <Head
        title="Compute servers"
        text="Live GPU usage and scheduling limits for the workshop workers."
      />
      <ErrorBox error={error || action.error} />
      <div className="server-grid">
        {servers?.map((s) => (
          <ServerCard
            key={s.id}
            server={s}
            onEdit={() => {
              setEditing(s);
              setConfig(structuredClone(s.config));
              setConfirmed(false);
            }}
          />
        ))}
      </div>
      {editing && config && (
        <div className="modal-backdrop">
          <section className="modal">
            <div className="section-title">
              <h2>{editing.name}</h2>
              <button
                aria-label="Close server settings"
                onClick={() => setEditing(undefined)}
              >
                <X />
              </button>
            </div>
            <div className="modal-content">
              <Toggle
                label="Enable new jobs"
                value={config.enabled}
                onChange={(v) => update("enabled", v)}
              />
              <Toggle
                label="Workshop training is authorized on this host"
                value={config.institutional_permission}
                onChange={(v) => update("institutional_permission", v)}
              />
              <div className="form-grid">
                <label>
                  Maximum environments per job
                  <select
                    value={config.max_envs}
                    onChange={(e) => update("max_envs", Number(e.target.value))}
                  >
                    {ENV_OPTIONS.map((n) => (
                      <option key={n} value={n}>
                        {n.toLocaleString()}
                      </option>
                    ))}
                  </select>
                </label>
                <Field
                  label="Concurrent jobs per GPU"
                  value={config.max_jobs}
                  min={1}
                  max={18}
                  onChange={(v) => update("max_jobs", v)}
                />
                <Field
                  label="Reserved GPU memory (MiB)"
                  value={config.reserve_mb}
                  onChange={(v) => update("reserve_mb", v)}
                />
                <Field
                  label="Memory margin (MiB)"
                  value={config.margin_mb}
                  min={256}
                  onChange={(v) => update("margin_mb", v)}
                />
              </div>
              <h3>CUDA MPS</h3>
              <Toggle
                label="Use the configured MPS service"
                value={config.mps_enabled}
                onChange={(v) => update("mps_enabled", v)}
              />
              {config.mps_enabled && (
                <>
                  <Toggle
                    label="Require MPS before starting a job"
                    value={config.mps_required}
                    onChange={(v) => update("mps_required", v)}
                  />
                  <label>
                    MPS interface
                    <select
                      value={config.mps_kind}
                      onChange={(e) => update("mps_kind", e.target.value)}
                    >
                      <option value="legacy">Legacy</option>
                      <option value="v3">MPS v3</option>
                    </select>
                  </label>
                  {[
                    "mps_pipe",
                    "mps_log",
                    ...(config.mps_kind === "v3"
                      ? ["mps_server", "mps_namespace"]
                      : []),
                  ].map((k) => (
                    <Field
                      key={k}
                      type="text"
                      label={k.replaceAll("_", " ")}
                      value={config[k] || ""}
                      onChange={(v) => update(k, v)}
                    />
                  ))}
                  <Field
                    label="Active thread percentage"
                    value={config.mps_threads}
                    min={1}
                    max={100}
                    onChange={(v) => update("mps_threads", v)}
                  />
                  <Field
                    label="Pinned device memory limit (MiB)"
                    value={config.mps_memory_mb}
                    onChange={(v) => update("mps_memory_mb", v)}
                  />
                </>
              )}
              <p className="info">{editing.inventory.mps?.reason}</p>
              {editing.quarantined && (
                <div className="reconcile">
                  <p>
                    Check the host and stop old workshop processes before
                    releasing their allocations.
                  </p>
                  <Toggle
                    label="All old workshop processes have stopped"
                    value={confirmed}
                    onChange={setConfirmed}
                  />
                  <Button
                    variant="danger"
                    disabled={!confirmed}
                    onClick={() =>
                      action.run(async () => {
                        await api(
                          "/admin/servers/" + editing.id + "/reconcile",
                          "POST",
                          { confirmed_all_processes_stopped: true },
                        );
                        setEditing(undefined);
                      }, "Server reconciled")
                    }
                  >
                    Release allocations
                  </Button>
                </div>
              )}
              <ErrorBox error={action.error} />
            </div>
            <div className="modal-footer">
              <span>Applies to future jobs.</span>
              <Button
                disabled={action.busy}
                onClick={() =>
                  action.run(async () => {
                    await api("/admin/servers/" + editing.id, "PUT", config);
                    setEditing(undefined);
                  })
                }
              >
                Save settings
              </Button>
            </div>
          </section>
        </div>
      )}
    </>
  );
}

function Participants() {
  const { data: users, error } = usePoll<User[]>(() => api("/admin/users"));
  const { data: mail } = usePoll<any>(() => api("/admin/email"));
  const [emails, setEmails] = useState(""),
    [limit, setLimit] = useState(2048),
    [edit, setEdit] = useState<User>(),
    [removing, setRemoving] = useState<User>(),
    [invite, setInvite] = useState(""),
    [credentials, setCredentials] = useState<any[]>([]),
    [sendEmails, setSendEmails] = useState(false),
    [search, setSearch] = useState("");
  const action = useAction();
  useEffect(() => {
    setSendEmails(!!mail?.configured);
  }, [mail?.configured]);
  const issue = async (id: string, send: boolean) => {
    const result = await api("/admin/users/" + id + "/password", "POST", {
      send_email: send,
    });
    setCredentials((previous) => [
      ...previous.filter((c) => c.email !== result.email),
      result,
    ]);
  };
  return (
    <>
      <Head
        title="Participants"
        text="Approve emails, choose an environment limit, and send account passwords. One outstanding run per person."
      />
      <ErrorBox error={error || action.error} />
      {!mail?.configured && (
        <section className="panel details">
          <h3>Email delivery needs setup</h3>
          <p>
            You can generate and copy passwords now. To send them, connect an
            email account in{" "}
            <Link to="/admin/settings">Workshop settings → Email delivery</Link>
            .
          </p>
        </section>
      )}
      <form
        className="panel details"
        onSubmit={(e) => {
          e.preventDefault();
          action.run(async () => {
            const list = [...new Set(emails.split(/[\s,;]+/).filter(Boolean))];
            const added = await api("/admin/users/bulk", "POST", {
              emails: list,
              env_limit: limit,
            });
            setEmails("");
            for (const id of added.user_ids) await issue(id, sendEmails);
          }, "Participant accounts prepared. Check delivery results below.");
        }}
      >
        <div className="form-grid">
          <label>
            Participant emails
            <textarea
              required
              rows={4}
              value={emails}
              onChange={(e) => setEmails(e.target.value)}
              placeholder="One email per line, or separated by commas"
            />
          </label>
          <label>
            Maximum environments
            <select
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
            >
              {ENV_OPTIONS.map((n) => (
                <option key={n} value={n}>
                  {n.toLocaleString()}
                </option>
              ))}
            </select>
          </label>
        </div>
        {mail?.configured && (
          <Toggle
            label="Email passwords after adding participants"
            value={sendEmails}
            onChange={setSendEmails}
          />
        )}
        <Button type="submit" disabled={action.busy}>
          <Plus size={16} />
          {action.busy
            ? "Preparing accounts…"
            : sendEmails
              ? "Add & email passwords"
              : "Add & generate passwords"}
        </Button>
      </form>
      {credentials.length > 0 && (
        <section className="panel details">
          <div className="section-title">
            <h3>Generated passwords</h3>
            <Button variant="secondary" onClick={() => setCredentials([])}>
              Dismiss passwords
            </Button>
          </div>
          <p>
            These are the passwords just generated. Copy them now; saved
            passwords cannot be retrieved. Resetting a password signs that
            participant out.
          </p>
          {credentials.map((c) => (
            <div className="panel details" key={c.email}>
              <strong>{c.email}</strong>
              <p>
                {c.delivery === "sent"
                  ? "Email accepted by the mail server."
                  : c.delivery === "failed"
                    ? "Email was not confirmed. Copy the password or fix email settings and try again."
                    : c.delivery === "development"
                      ? "Development outbox only — no email sent."
                      : "Password generated; email not requested."}
              </p>
              <div className="token-row">
                <input
                  readOnly
                  value={c.password}
                  aria-label={"New password for " + c.email}
                />
                <Button
                  variant="secondary"
                  onClick={() =>
                    navigator.clipboard.writeText(
                      `Sign in: ${c.url}\nEmail: ${c.email}\nPassword: ${c.password}`,
                    )
                  }
                >
                  <Copy size={15} />
                  Copy login
                </Button>
                <Button
                  disabled={action.busy}
                  onClick={() =>
                    action.run(async () => {
                      const result = await api(
                        "/admin/users/" + c.user_id + "/password/email",
                        "POST",
                        { password: c.password },
                      );
                      setCredentials((previous) =>
                        previous.map((entry) =>
                          entry.user_id === c.user_id
                            ? { ...entry, ...result }
                            : entry,
                        ),
                      );
                    }, "")
                  }
                >
                  {c.delivery === "sent" ? "Send again" : "Send this password"}
                </Button>
              </div>
            </div>
          ))}
        </section>
      )}
      {invite && (
        <section className="panel details">
          <h3>Participant sign-in link</h3>
          <p>Single use; expires in 15 minutes.</p>
          <div className="token-row">
            <input readOnly value={invite} />
            <Button
              variant="secondary"
              onClick={() => navigator.clipboard.writeText(invite)}
            >
              <Copy size={15} />
              Copy
            </Button>
            <button onClick={() => setInvite("")} aria-label="Dismiss link">
              <X size={17} />
            </button>
          </div>
        </section>
      )}
      <section className="panel">
        <div className="details">
          <label>
            Find participant
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search email"
            />
          </label>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Email</th>
                <th>Role</th>
                <th>Access</th>
                <th>Environment limit</th>
                <th>Credential email</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {users
                ?.filter((u) =>
                  u.email.toLowerCase().includes(search.toLowerCase()),
                )
                .map((u) => (
                  <tr key={u.id}>
                    <td>{u.email}</td>
                    <td>{u.role}</td>
                    <td>
                      <Badge status={u.approved ? "APPROVED" : "DISABLED"} />
                    </td>
                    <td>
                      {u.env_limit?.toLocaleString() || "Workshop default"}
                    </td>
                    <td>
                      {u.credential_email_at
                        ? date(u.credential_email_at)
                        : "Not sent"}
                    </td>
                    <td>
                      <div className="actions">
                        <Button
                          variant="secondary small"
                          disabled={action.busy}
                          onClick={() => setEdit({ ...u })}
                        >
                          Edit
                        </Button>
                        {u.approved && u.role === "participant" && (
                          <>
                            <Button
                              variant="secondary small"
                              disabled={action.busy}
                              onClick={() =>
                                action.run(() => issue(u.id, false), "")
                              }
                            >
                              Generate password
                            </Button>
                            <Button
                              variant="secondary small"
                              disabled={action.busy || !mail?.configured}
                              onClick={() =>
                                action.run(() => issue(u.id, true), "")
                              }
                            >
                              Reset & email password
                            </Button>
                            <Button
                              variant="secondary small"
                              disabled={action.busy}
                              onClick={() =>
                                action.run(
                                  async () =>
                                    setInvite(
                                      (
                                        await api(
                                          "/admin/users/" + u.id + "/invite",
                                          "POST",
                                        )
                                      ).url,
                                    ),
                                  "",
                                )
                              }
                            >
                              Sign-in link
                            </Button>
                          </>
                        )}
                        {u.role === "participant" && (
                          <Button
                            variant="danger small"
                            disabled={action.busy}
                            onClick={() => setRemoving(u)}
                          >
                            Delete
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </section>
      {edit && (
        <div className="modal-backdrop">
          <section className="modal compact">
            <div className="section-title">
              <h2>{edit.email}</h2>
              <button
                onClick={() => setEdit(undefined)}
                aria-label="Close participant settings"
              >
                <X />
              </button>
            </div>
            <div className="modal-content">
              <Toggle
                label="Approved"
                value={!!edit.approved}
                onChange={(v) => setEdit({ ...edit, approved: v })}
              />
              <label>
                Maximum environments
                <select
                  value={edit.env_limit ?? ""}
                  onChange={(e) =>
                    setEdit({
                      ...edit,
                      env_limit: e.target.value ? Number(e.target.value) : null,
                    })
                  }
                >
                  <option value="">Workshop default</option>
                  {ENV_OPTIONS.map((n) => (
                    <option key={n} value={n}>
                      {n.toLocaleString()}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Role
                <select
                  value={edit.role}
                  onChange={(e) => setEdit({ ...edit, role: e.target.value })}
                >
                  <option value="participant">Participant</option>
                  <option value="admin">Admin</option>
                </select>
              </label>
              <ErrorBox error={action.error} />
            </div>
            <div className="modal-footer">
              <Button
                disabled={action.busy}
                onClick={() =>
                  action.run(async () => {
                    await api("/admin/users/" + edit.id, "PUT", {
                      approved: !!edit.approved,
                      role: edit.role,
                      env_limit: edit.env_limit,
                    });
                    setEdit(undefined);
                  })
                }
              >
                Save participant
              </Button>
            </div>
          </section>
        </div>
      )}
      {removing && (
        <div className="modal-backdrop">
          <section className="modal compact">
            <div className="section-title">
              <h2>Delete participant</h2>
              <button
                onClick={() => setRemoving(undefined)}
                aria-label="Close delete dialog"
              >
                <X />
              </button>
            </div>
            <div className="modal-content">
              <p>
                Delete <strong>{removing.email}</strong>?
              </p>
              <p>
                This removes their access and cancels queued jobs. Active jobs
                receive a stop request. Past runs remain available to
                administrators.
              </p>
              <ErrorBox error={action.error} />
            </div>
            <div className="modal-footer">
              <Button
                variant="secondary"
                onClick={() => setRemoving(undefined)}
              >
                Keep participant
              </Button>
              <Button
                variant="danger"
                disabled={action.busy}
                onClick={() =>
                  action.run(async () => {
                    await api("/admin/users/" + removing.id, "DELETE");
                    setCredentials((previous) =>
                      previous.filter((c) => c.email !== removing.email),
                    );
                    setRemoving(undefined);
                  }, "Participant deleted")
                }
              >
                Delete participant
              </Button>
            </div>
          </section>
        </div>
      )}
    </>
  );
}

function EmailDelivery() {
  const { data, error } = usePoll<any>(() => api("/admin/email"), [], 30000);
  const [form, setForm] = useState<any>();
  const action = useAction();
  useEffect(() => {
    if (data && !form)
      setForm({
        ...data,
        host: data.host || "smtp.gmail.com",
        port: data.port || 587,
        security: data.security || "starttls",
        password: "",
      });
  }, [data]);
  const update = (key: string, value: any) =>
    setForm({ ...form, [key]: value });
  if (!form) return <ErrorBox error={error} />;
  return (
    <section className="panel details">
      <h2>Email delivery</h2>
      <p>
        {data?.configured
          ? "An email account is configured. Use Send test email to verify sending."
          : "Connect one email account to send participant passwords. For Gmail, use an app password."}
      </p>
      <p>
        <a
          href="https://support.google.com/mail/answer/185833"
          target="_blank"
          rel="noreferrer"
        >
          Google app-password instructions
        </a>
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          action.run(async () => {
            const saved = await api("/admin/email", "PUT", {
              host: form.host,
              port: form.port,
              security: form.security,
              sender: form.sender,
              username: form.username,
              password: form.password,
            });
            setForm({ ...form, ...saved, password: "" });
          }, "Email connection verified and saved");
        }}
      >
        <div className="form-grid">
          <label>
            SMTP server
            <input
              required
              value={form.host}
              onChange={(e) => update("host", e.target.value)}
              placeholder="smtp.gmail.com"
            />
          </label>
          <label>
            Connection
            <select
              value={form.security}
              onChange={(e) =>
                setForm({
                  ...form,
                  security: e.target.value,
                  port: e.target.value === "ssl" ? 465 : 587,
                })
              }
            >
              <option value="starttls">STARTTLS · port 587</option>
              <option value="ssl">TLS · port 465</option>
            </select>
          </label>
          <label>
            Sender email
            <input
              required
              type="email"
              value={form.sender}
              onChange={(e) => update("sender", e.target.value)}
              placeholder="your-address@gmail.com"
            />
          </label>
          <label>
            Account username
            <input
              value={form.username}
              onChange={(e) => update("username", e.target.value)}
              autoComplete="off"
            />
          </label>
          <label>
            App password
            <input
              type="password"
              value={form.password}
              onChange={(e) => update("password", e.target.value)}
              autoComplete="new-password"
              placeholder={
                data?.has_password
                  ? "Saved — leave blank to keep"
                  : "Enter privately here"
              }
            />
          </label>
        </div>
        <ErrorBox error={action.error || error} />
        <div className="actions">
          <Button type="submit" disabled={action.busy}>
            Verify & save email account
          </Button>
          <Button
            variant="secondary"
            disabled={action.busy || !(form.configured || data?.configured)}
            onClick={() =>
              action.run(async () => {
                const result = await api("/admin/email/test", "POST");
                if (result.delivery !== "sent")
                  throw new Error("Development outbox only; no email sent.");
              }, "Test email accepted by the mail server")
            }
          >
            Send test email to me
          </Button>
        </div>
      </form>
    </section>
  );
}
function WorkshopSettings() {
  const { data, error } = usePoll<any>(() => api("/admin/settings"), [], 30000);
  const [form, setForm] = useState<any>();
  const action = useAction();
  useEffect(() => {
    if (data && !form) {
      setForm(structuredClone(data));
    }
  }, [data]);
  const update = (key: string, v: any) => setForm({ ...form, [key]: v });
  const updateEnvironmentRange = (key: string, value: number) => {
    const next = { ...form, [key]: value };
    if (key === "max_envs") next.min_envs = Math.min(next.min_envs, value);
    if (key === "min_envs") next.max_envs = Math.max(next.max_envs, value);
    next.presets = ENV_OPTIONS.filter(
      (n) => n >= next.min_envs && n <= next.max_envs,
    );
    if (!next.presets.includes(next.default_envs))
      next.default_envs = next.presets[0];
    setForm(next);
  };

  return (
    <>
      <Head
        title="Workshop settings"
        text="Set environment limits and the maximum number of concurrent training jobs."
      />
      <ErrorBox error={error || action.error} />
      <EmailDelivery />
      {form && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            action.run(
              () =>
                api("/admin/settings", "PUT", {
                  ...form,
                  presets: form.presets,
                }),
              "Workshop settings saved",
            );
          }}
        >
          <section className="panel details">
            <h2>Training limits</h2>
            <div className="form-grid">
              <label>
                Default environments
                <select
                  value={form.default_envs}
                  onChange={(e) =>
                    update("default_envs", Number(e.target.value))
                  }
                >
                  {form.presets.map((n: number) => (
                    <option key={n} value={n}>
                      {n.toLocaleString()}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Maximum environments per participant
                <select
                  value={form.max_envs}
                  onChange={(e) =>
                    updateEnvironmentRange("max_envs", Number(e.target.value))
                  }
                >
                  {ENV_OPTIONS.map((n) => (
                    <option key={n} value={n}>
                      {n.toLocaleString()}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Minimum environments
                <select
                  value={form.min_envs}
                  onChange={(e) =>
                    updateEnvironmentRange("min_envs", Number(e.target.value))
                  }
                >
                  {ENV_OPTIONS.map((n) => (
                    <option key={n} value={n}>
                      {n.toLocaleString()}
                    </option>
                  ))}
                </select>
              </label>
              <Field
                label="Maximum concurrent jobs"
                value={form.max_running_jobs}
                min={1}
                max={100}
                onChange={(v) => update("max_running_jobs", v)}
              />
              <Field
                label="Maximum GPU memory usage (%)"
                value={form.gpu_memory_percent}
                min={10}
                max={95}
                onChange={(v) => update("gpu_memory_percent", v)}
              />
              <Field
                label="Maximum iterations per run"
                value={form.max_iterations}
                min={1}
                max={100000}
                onChange={(v) => update("max_iterations", v)}
              />
              <label>
                Available environment sizes
                <div className="environment-options">
                  {form.presets.map((n: number) => (
                    <span className="preset-pill" key={n}>
                      {n.toLocaleString()}
                    </span>
                  ))}
                </div>
                <small>Powers of two within the workshop limits.</small>
              </label>
            </div>
            <p>
              Job capacity is calculated from free GPU memory, including other
              users’ processes and starting jobs. The stricter memory reserve
              still applies. Existing jobs keep their saved settings.
            </p>
            <Toggle
              label="Pause new job scheduling"
              value={form.paused}
              onChange={(v) => update("paused", v)}
            />
          </section>
          <section className="panel details">
            <h2>Memory estimate</h2>
            <p>
              Used for admission until the workload is benchmarked. Each host
              also keeps its configured reserve and margin.
            </p>
            <div className="form-grid three">
              {[
                ["base_mb", "Base memory (MiB)"],
                ["per_env_mb", "Memory per environment (MiB)"],
                ["safety_factor", "Safety factor"],
              ].map(([key, label]) => (
                <Field
                  key={key}
                  label={label}
                  value={form.memory_profiles[key]}
                  min={key === "safety_factor" ? 1 : 0}
                  onChange={(v) =>
                    update("memory_profiles", {
                      ...form.memory_profiles,
                      [key]: v,
                    })
                  }
                />
              ))}
            </div>
          </section>
          <div className="savebar">
            <Link to="/motions" className="text-link">
              Manage motion library <ArrowRight size={14} />
            </Link>
            <Button type="submit" disabled={action.busy}>
              Save settings <Check size={16} />
            </Button>
          </div>
        </form>
      )}
    </>
  );
}

function App() {
  const [user, setUser] = useState<User | null>(null),
    [loading, setLoading] = useState(true),
    [notice, setNotice] = useState("");
  const reload = useCallback(async () => {
    try {
      setUser(await api("/me"));
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    reload();
  }, []);
  useEffect(() => {
    if (notice) {
      const timer = setTimeout(() => setNotice(""), 4500);
      return () => clearTimeout(timer);
    }
  }, [notice]);
  if (loading)
    return (
      <div className="boot">
        <Cpu />
        <span>Loading…</span>
      </div>
    );
  return (
    <Auth.Provider value={{ user, reload }}>
      <Notice.Provider value={setNotice}>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Navigate to="/login" />} />
            <Route path="/*" element={<Shell />} />
          </Routes>
        </BrowserRouter>
        {notice && (
          <div className="toast" role="status">
            <Check size={16} />
            {notice}
          </div>
        )}
      </Notice.Provider>
    </Auth.Provider>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
