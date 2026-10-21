import React, {
  useState,
  useEffect,
  useCallback,
  createContext,
  useContext,
} from "react";
import { createRoot } from "react-dom/client";
import {
  BrowserRouter,
  Routes,
  Route,
  NavLink,
  Link,
  Navigate,
  useNavigate,
  useParams,
  useLocation,
} from "react-router-dom";
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Check,
  ChevronRight,
  Code2,
  Copy,
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
  Terminal,
  Users,
  X,
  AlertCircle,
  Clock,
  Box,
  RefreshCw,
  Zap,
} from "lucide-react";
import hljs from "highlight.js/lib/common";
import { api, User, Run, active, date, duration } from "./api";
import "./style.css";

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
    let live = true;
    const update = async () => {
      try {
        const result = await fn();
        if (live) {
          setData(result);
          setError("");
        }
      } catch (e) {
        if (live) setError(String((e as Error).message));
      }
    };
    update();
    const t = setInterval(update, interval);
    return () => {
      live = false;
      clearInterval(t);
    };
  }, deps);
  return { data, error };
}
function ErrorBox({ error }: { error?: string }) {
  return error ? (
    <div className="error">
      <AlertCircle size={17} />
      {error}
    </div>
  ) : null;
}
function Badge({ status }: { status: string }) {
  return (
    <span className={"badge " + status.toLowerCase()}>
      <i />
      {status.toLowerCase().replace("_", " ")}
    </span>
  );
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
function PageHead({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <header className="page-head">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {action}
    </header>
  );
}
function Stat({
  label,
  value,
  icon: Icon,
  detail,
}: {
  label: string;
  value: React.ReactNode;
  icon: React.ElementType;
  detail?: string;
}) {
  return (
    <div className="stat">
      <div className="stat-top">
        {label}
        <Icon size={17} />
      </div>
      <strong>{value}</strong>
      {detail && <small>{detail}</small>}
    </div>
  );
}
function Empty({
  title,
  children,
}: {
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <Box size={32} />
      <h3>{title}</h3>
      {children}
    </div>
  );
}
function useAction() {
  const notify = useContext(Notice);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
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

function Login({ register = false }: { register?: boolean }) {
  const { user, reload } = useContext(Auth);
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const { busy, error, run } = useAction();
  const token = new URLSearchParams(location.hash.slice(1)).get("token");
  useEffect(() => {
    if (token) {
      history.replaceState(null, "", "/login");
      run(async () => {
        await api("/auth/verify", "POST", { token });
        await reload();
        nav("/dashboard");
      }, "");
    }
  }, []);
  if (user) return <Navigate to="/dashboard" />;
  return (
    <div className="auth-page">
      <div className="auth-art">
        <Link to="/login" className="brand">
          <span className="brand-mark">
            <Cpu size={24} />
          </span>
          Robot Training Hub
        </Link>
        <div className="auth-copy">
          <span className="pill">HUMANOID REINFORCEMENT LEARNING</span>
          <h1>
            Small experiments.
            <br />
            Big steps forward.
          </h1>
          <p>
            A shared workspace to train, understand, and explore the Booster K1.
            Your laptop is all you need.
          </p>
          <div className="robot-orbit">
            <Robot />
          </div>
          <span className="auth-foot">
            BOOSTER K1 &nbsp; / &nbsp; MJLAB WORKSHOP
          </span>
        </div>
      </div>
      <div className="auth-form">
        <div className="mobile-brand">Robot Training Hub</div>
        <span className="eyebrow">YOUR WORKSHOP WORKSPACE</span>
        <h1>{register ? "Join the workshop" : "Welcome back."}</h1>
        <p>
          {register
            ? "Register your email. Your workshop administrator will approve access."
            : "Sign in with a secure link sent to your approved email."}
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            run(async () => {
              const r = await api(
                "/auth/" + (register ? "register" : "request"),
                "POST",
                { email },
              );
              setMessage(r.message);
            }, "");
          }}
        >
          <label>
            Email address
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@university.edu"
              required
              autoComplete="email"
            />
          </label>
          <Button type="submit" disabled={busy}>
            {busy
              ? "Please wait…"
              : register
                ? "Request workshop access"
                : "Send sign-in link"}
            <ArrowRight size={17} />
          </Button>
        </form>
        <ErrorBox error={error} />
        {message && (
          <div className="success">
            <Check size={18} />
            {message}
          </div>
        )}
        <p className="auth-switch">
          {register ? "Already registered?" : "New to the workshop?"}{" "}
          <Link to={register ? "/login" : "/register"}>
            {register ? "Sign in" : "Request access"}
          </Link>
        </p>
        <div className="auth-note">
          <ShieldCheck size={19} />
          <span>
            No password to remember.
            <br />
            Your sign-in link expires in 15 minutes.
          </span>
        </div>
      </div>
    </div>
  );
}
function Robot() {
  return (
    <svg
      viewBox="0 0 320 330"
      className="robot"
      aria-label="Illustration of a Booster K1 humanoid robot"
    >
      <defs>
        <linearGradient id="metal" x1="0" y1="0" x2="1" y2="1">
          <stop stopColor="#e3f7ed" />
          <stop offset="1" stopColor="#8aa8a0" />
        </linearGradient>
      </defs>
      <ellipse cx="162" cy="303" rx="89" ry="12" fill="#103c36" />
      <g stroke="#214941" strokeWidth="3" strokeLinejoin="round">
        <path
          d="M128 96L115 148 129 183H194L207 148 194 96Z"
          fill="url(#metal)"
        />
        <rect
          x="134"
          y="44"
          width="55"
          height="47"
          rx="18"
          fill="url(#metal)"
        />
        <rect x="140" y="56" width="43" height="15" rx="7" fill="#133b36" />
        <path d="M149 62h7m9 0h7" stroke="#9be4b3" />
        <rect x="151" y="88" width="23" height="10" rx="4" fill="#214c43" />
        <circle cx="117" cy="111" r="14" fill="#66877d" />
        <circle cx="204" cy="111" r="14" fill="#66877d" />
        <path
          d="M104 115L90 158 101 181 114 166 125 119M198 121L215 160 205 179 194 163"
          fill="url(#metal)"
        />
        <path
          d="M94 179l-4 40 13 6 11-42M209 178l18 38-13 7-19-41"
          fill="url(#metal)"
        />
        <circle cx="105" cy="175" r="10" fill="#284f45" />
        <circle cx="204" cy="175" r="10" fill="#284f45" />
        <path
          d="M128 183L128 227 150 235 159 187M166 187L171 231 195 224 194 183"
          fill="#a6c1b5"
        />
        <circle cx="139" cy="232" r="12" fill="#285347" />
        <circle cx="182" cy="232" r="12" fill="#285347" />
        <path
          d="M126 243l1 45h24l-1-44M171 244l3 44h25l-5-47"
          fill="url(#metal)"
        />
        <path
          d="M126 285l-12 14h40v-14M174 285l-1 14h38l-13-14"
          fill="#63877c"
        />
        <path d="M141 116h41l-4 32h-32Z" fill="#376459" />
        <path d="M151 129h19" stroke="#b0efb9" strokeWidth="4" />
        <circle cx="161" cy="168" r="5" fill="#3a6d58" />
      </g>
      <g fill="#a0d6ad">
        <circle cx="65" cy="105" r="3" />
        <circle cx="258" cy="193" r="3" />
        <circle cx="239" cy="59" r="2" />
      </g>
      <g stroke="#43725e" strokeWidth="1" fill="none">
        <path d="M202 67h44l13-12M109 255H65l-13 15" />
        <circle cx="260" cy="54" r="5" />
        <circle cx="49" cy="273" r="5" />
      </g>
    </svg>
  );
}

function Shell() {
  const { user, reload } = useContext(Auth);
  const [mobile, setMobile] = useState(false);
  const loc = useLocation();
  useEffect(() => setMobile(false), [loc.pathname]);
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
      <aside className={mobile ? "sidebar open" : "sidebar"}>
        <Link to="/dashboard" className="brand">
          <span className="brand-mark">
            <Cpu size={23} />
          </span>
          <span>
            Robot Training<span className="brand-second">Hub</span>
          </span>
        </Link>
        <div className="workspace">
          <span className="workspace-icon">
            <FlaskConical size={19} />
          </span>
          <div>
            K1 Workshop<small>Reinforcement learning lab</small>
          </div>
          <ChevronRight size={15} />
        </div>
        <span className="nav-label">WORKSPACE</span>
        <nav>
          <NavLink to="/dashboard">
            <LayoutDashboard />
            Overview
          </NavLink>
          <NavLink to="/train/new">
            <Plus />
            New training
          </NavLink>
          <NavLink to="/runs" end>
            <Activity />
            My trainings
          </NavLink>
          <NavLink to="/code">
            <Code2 />
            Training code
          </NavLink>
        </nav>
        {user.role === "admin" && (
          <>
            <span className="nav-label admin-label">ADMINISTRATION</span>
            <nav>
              <NavLink to="/admin" end>
                <ShieldCheck />
                Workshop overview
              </NavLink>
              <NavLink to="/admin/runs">
                <Layers />
                All training runs
              </NavLink>
              <NavLink to="/admin/servers">
                <Server />
                Compute & MPS
              </NavLink>
              <NavLink to="/admin/users">
                <Users />
                Participants
              </NavLink>
              <NavLink to="/admin/settings">
                <Settings2 />
                Workshop settings
              </NavLink>
            </nav>
          </>
        )}
        <div className="sidebar-bottom">
          <div className="learn-card">
            <BookOpen size={19} />
            <b>Learn by doing</b>
            <p>Every run includes the real source code behind your robot.</p>
            <Link to="/code">
              Explore the code <ArrowUpRight size={15} />
            </Link>
          </div>
          <div className="profile">
            <span className="avatar">
              {user.email.slice(0, 2).toUpperCase()}
            </span>
            <div>
              <b>{user.email.split("@")[0]}</b>
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
            Workspace <ChevronRight size={13} />
            <b>
              {loc.pathname.startsWith("/admin")
                ? "Administration"
                : "K1 workshop"}
            </b>
          </div>
          <span>
            <i className="online-dot" />
            Workshop workspace
          </span>
        </div>
        <div className="content">
          <Routes>
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/train/new" element={<NewTraining />} />
            <Route path="/runs" element={<RunsPage />} />
            <Route path="/runs/:id" element={<RunPage />} />
            <Route path="/runs/:id/code" element={<CodePage />} />
            <Route path="/code" element={<CodePage />} />
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
            <Route path="*" element={<Navigate to="/dashboard" />} />
          </Routes>
          <footer className="footer">
            <span>ROBOT TRAINING HUB</span>
            <span>Booster K1 · Powered by mjlab</span>
          </footer>
        </div>
      </main>
    </div>
  );
}

function Dashboard() {
  const { user } = useContext(Auth);
  const { data: runs, error } = usePoll<Run[]>(() => api("/runs"));
  const own = runs?.filter((r) => r.email === user?.email) || [];
  const running = own.find(active);
  return (
    <>
      <PageHead
        eyebrow="YOUR LEARNING WORKSPACE"
        title={`Let's make progress, ${user?.email.split("@")[0]}.`}
        description="Train a humanoid. Explore the code. See what changes."
        action={
          <Link className="button" to="/train/new">
            <Plus size={17} />
            New training
          </Link>
        }
      />
      <ErrorBox error={error} />
      <section className="hero">
        <div className="hero-copy">
          <span className="pill">BOOSTER K1 · MOTION TRACKING</span>
          <h2>
            Your next idea,
            <br />
            in motion.
          </h2>
          <p>
            Turn motion capture into learned behavior. We handle the compute so
            you can focus on the experiment.
          </p>
          <Link to="/train/new" className="button light">
            Start an experiment <ArrowRight size={16} />
          </Link>
          <div className="hero-note">
            <ShieldCheck size={15} />
            No setup. No SSH. Just exploration.
          </div>
        </div>
        <div className="hero-visual">
          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <Robot />
          <div className="robot-label">
            <span className="online-dot" />
            Booster K1 <small>22 degrees of freedom</small>
          </div>
        </div>
      </section>
      <div className="stats">
        <Stat
          label="Your experiments"
          value={own.length}
          icon={FlaskConical}
          detail="Every idea starts with a run"
        />
        <Stat
          label="Completed"
          value={own.filter((r) => r.status === "COMPLETED").length}
          icon={Check}
          detail="Ready to explore and download"
        />
        <Stat
          label="Active experiment"
          value={running ? running.status.toLowerCase() : "Ready to train"}
          icon={Activity}
          detail={
            running?.queue_position
              ? `Position ${running.queue_position} in queue`
              : "One experiment at a time"
          }
        />
      </div>
      {running && (
        <section className="panel active-panel">
          <div className="section-title">
            <h2>Your active experiment</h2>
            <Badge status={running.status} />
          </div>
          <div className="active-content">
            <span className="experiment-icon">
              <Activity />
            </span>
            <div>
              <Link to={"/runs/" + running.id}>
                <h3>{running.name}</h3>
              </Link>
              <p>
                {running.spec.num_envs.toLocaleString()} environments ·{" "}
                {running.server_name || "Waiting for available compute"}
              </p>
            </div>
            <div className="active-progress">
              <b>
                {Math.round(
                  (running.iteration / running.spec.iterations) * 100,
                )}
                %
              </b>
              <progress
                max={running.spec.iterations}
                value={running.iteration}
              />
            </div>
            <Link to={"/runs/" + running.id} className="button secondary">
              Open run <ArrowRight size={16} />
            </Link>
          </div>
        </section>
      )}
      <section className="panel">
        <div className="section-title">
          <div>
            <h2>Recent experiments</h2>
            <p>Your work, from first step to final checkpoint.</p>
          </div>
          <Link to="/runs" className="text-link">
            View all runs <ArrowRight size={15} />
          </Link>
        </div>
        <RunTable runs={own.slice(0, 5)} />
      </section>
      <div className="two-col">
        <Link to="/code" className="resource-card">
          <span className="resource-icon">
            <Code2 />
          </span>
          <div>
            <h3>See what makes it move</h3>
            <p>
              Browse the reward functions, task configuration, and training
              pipeline.
            </p>
            <b>
              Explore training code <ArrowUpRight size={15} />
            </b>
          </div>
        </Link>
        <div className="resource-card">
          <span className="resource-icon sand">
            <Layers />
          </span>
          <div>
            <h3>A little experimentation goes a long way</h3>
            <p>
              Change one parameter, compare the reward curve, and learn from
              each run. Your source is saved automatically.
            </p>
          </div>
        </div>
      </div>
    </>
  );
}

function RunTable({ runs, admin = false }: { runs: Run[]; admin?: boolean }) {
  if (!runs.length)
    return (
      <Empty title="Your next experiment starts here">
        <p>Launch a training run to see its progress and results.</p>
        <Link className="button secondary" to="/train/new">
          Start training <Plus size={16} />
        </Link>
      </Empty>
    );
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Experiment</th>
            {admin && <th>Participant</th>}
            <th>Status</th>
            <th>Environment / motion</th>
            <th>Compute</th>
            <th>Progress</th>
            <th>{admin ? "Started / memory" : "Elapsed"}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id}>
              <td>
                <Link className="run-name" to={"/runs/" + r.id}>
                  {r.name}
                </Link>
                <small className="mono">
                  {r.id.slice(0, 8)}
                  {admin && ` · priority ${r.priority}`}
                </small>
              </td>
              {admin && <td>{r.email}</td>}
              <td>
                <Badge status={r.status} />
                {r.cancel && active(r) && <small>Stopping requested</small>}
              </td>
              <td>
                {r.spec.num_envs.toLocaleString()} envs
                <small>{r.spec.motion.label}</small>
              </td>
              <td>
                {r.server_name || "Auto assignment"}
                <small>{r.gpu?.slice(0, 18) || "Queued for capacity"}</small>
              </td>
              <td>
                <div className="mini-progress">
                  <span>
                    {r.iteration.toLocaleString()} /{" "}
                    {r.spec.iterations.toLocaleString()}
                  </span>
                  <progress value={r.iteration} max={r.spec.iterations} />
                </div>
              </td>
              <td>
                {admin ? date(r.started) : duration(r)}
                {admin && <small>{r.gpu_mb} MiB</small>}
              </td>
              <td>
                <Link aria-label={"Open " + r.name} to={"/runs/" + r.id}>
                  <ArrowUpRight size={18} />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function RunsPage({ admin = false }: { admin?: boolean }) {
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const { data, error } = usePoll<Run[]>(
    () =>
      api(`/runs?${new URLSearchParams({ q, ...(status ? { status } : {}) })}`),
    [status, q],
  );
  return (
    <>
      <PageHead
        eyebrow={admin ? "ADMINISTRATION" : "YOUR WORKSPACE"}
        title={admin ? "All training runs" : "My trainings"}
        description={
          admin
            ? "Inspect every experiment, manage the queue, and follow workshop progress."
            : "A complete record of your experiments and what they learned."
        }
        action={
          <Link className="button" to="/train/new">
            <Plus size={16} />
            New training
          </Link>
        }
      />
      <ErrorBox error={error} />
      <section className="panel">
        <div className="filterbar">
          <div className="search">
            <Search size={17} />
            <input
              aria-label="Search training runs"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search experiments, IDs, or participants…"
            />
          </div>
          <select
            aria-label="Filter status"
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
          <span className="muted">{data?.length || 0} runs</span>
        </div>
        {data ? (
          <RunTable runs={data} admin={admin} />
        ) : (
          <p className="loading">Loading experiments…</p>
        )}
      </section>
    </>
  );
}

function NewTraining() {
  const { data: options, error } = usePoll<any>(
    () => api("/options"),
    [],
    15000,
  );
  const { data: runs } = usePoll<Run[]>(() => api("/runs"));
  const { user } = useContext(Auth);
  const nav = useNavigate();
  const action = useAction();
  const [name, setName] = useState("");
  const [motion, setMotion] = useState("");
  const [envs, setEnvs] = useState(0);
  const [iterations, setIterations] = useState(200);
  const [advanced, setAdvanced] = useState(false);
  const [lr, setLr] = useState("");
  const [rewards, setRewards] = useState<Record<string, string>>({});
  useEffect(() => {
    if (options) {
      setEnvs(options.default_envs);
      setMotion(options.motions[0]?.id || "");
    }
  }, [!!options]);
  const outstanding = runs?.find((r) => r.email === user?.email && active(r));
  return (
    <>
      <PageHead
        eyebrow="NEW EXPERIMENT"
        title="Set your robot in motion."
        description="Choose a motion and a training budget. We'll find the right GPU."
      />
      <ErrorBox error={error || action.error} />
      {outstanding && (
        <div className="warning">
          <Clock size={18} />
          <span>
            You already have an outstanding run.{" "}
            <Link to={"/runs/" + outstanding.id}>Open {outstanding.name}</Link>{" "}
            to follow or stop it.
          </span>
        </div>
      )}
      {options && (
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
                seed: 42,
                ...(lr ? { learning_rate: Number(lr) } : {}),
                rewards: Object.fromEntries(
                  Object.entries(rewards)
                    .filter(([, v]) => v !== "")
                    .map(([k, v]) => [k, Number(v)]),
                ),
              });
              nav("/runs/" + r.id);
            }, "Training submitted");
          }}
        >
          <section className="panel form-panel">
            <div className="form-section">
              <span className="step">01</span>
              <div>
                <h2>Name your experiment</h2>
                <p>
                  Pick a name that helps you remember what you are exploring.
                </p>
                <label>
                  Experiment name
                  <input
                    required
                    maxLength={80}
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. First steps · foot tracking"
                  />
                </label>
              </div>
            </div>
            <div className="form-section">
              <span className="step">02</span>
              <div>
                <h2>Choose a motion</h2>
                <p>Train Booster K1 to follow an approved motion artifact.</p>
                <label>
                  Task
                  <select>
                    <option>Mjlab-Tracking-Flat-Booster-K1</option>
                  </select>
                </label>
                <label>
                  Motion artifact
                  <select
                    required
                    value={motion}
                    onChange={(e) => setMotion(e.target.value)}
                  >
                    <option value="" disabled>
                      Select an approved motion
                    </option>
                    {options.motions.map((m: any) => (
                      <option key={m.id} value={m.id}>
                        {m.label}
                      </option>
                    ))}
                  </select>
                </label>
                {!options.motions.length && (
                  <div className="warning">
                    An administrator needs to approve a versioned motion
                    artifact first.
                  </div>
                )}
                <span className="field-note mono">
                  {options.motions.find((m: any) => m.id === motion)?.artifact}
                </span>
              </div>
            </div>
            <div className="form-section">
              <span className="step">03</span>
              <div>
                <h2>Set your training budget</h2>
                <p>
                  More parallel environments collect more experience at once.
                </p>
                <label>Parallel environments</label>
                <div className="presets">
                  {options.presets
                    .filter(
                      (n: number) =>
                        n <= (options.user_env_limit ?? options.max_envs),
                    )
                    .map((n: number) => (
                      <button
                        type="button"
                        key={n}
                        className={envs === n ? "preset selected" : "preset"}
                        onClick={() => setEnvs(n)}
                      >
                        {n.toLocaleString()}
                        {n === options.default_envs && <small>Default</small>}
                      </button>
                    ))}
                </div>
                <label>
                  Training iterations
                  <input
                    type="number"
                    required
                    min={1}
                    max={options.max_iterations}
                    value={iterations}
                    onChange={(e) => setIterations(Number(e.target.value))}
                  />
                  <small>
                    Between 1 and {options.max_iterations.toLocaleString()}{" "}
                    iterations.
                  </small>
                </label>
                <button
                  type="button"
                  className="advanced-toggle"
                  onClick={() => setAdvanced(!advanced)}
                >
                  <Settings2 size={16} />
                  Approved advanced parameters{" "}
                  <ChevronRight
                    size={15}
                    className={advanced ? "rotate" : ""}
                  />
                </button>
                {advanced && (
                  <div className="advanced-fields">
                    <label>
                      Learning rate
                      <input
                        type="number"
                        step="any"
                        value={lr}
                        min={options.learning_rate_bounds[0]}
                        max={options.learning_rate_bounds[1]}
                        placeholder="Use task default"
                        onChange={(e) => setLr(e.target.value)}
                      />
                    </label>
                    {Object.entries(options.reward_bounds).map(
                      ([key, bounds]: any) => (
                        <label key={key}>
                          {key} weight
                          <input
                            type="number"
                            step="any"
                            value={rewards[key] || ""}
                            placeholder="Use task default"
                            min={bounds[0]}
                            max={bounds[1]}
                            onChange={(e) =>
                              setRewards({ ...rewards, [key]: e.target.value })
                            }
                          />
                          <small>Approved range: {bounds.join(" to ")}</small>
                        </label>
                      ),
                    )}
                  </div>
                )}
              </div>
            </div>
            <div className="form-submit">
              <span>
                <ShieldCheck size={16} />
                Exact source code saved with your run
              </span>
              <Button
                type="submit"
                disabled={!!outstanding || action.busy || !motion}
              >
                {action.busy ? "Preparing snapshot…" : "Start training"}
                <ArrowRight size={16} />
              </Button>
            </div>
          </section>
          <aside className="training-aside">
            <div className="panel summary">
              <div className="eyebrow">EXPERIMENT SUMMARY</div>
              <Robot />
              <h3>Booster K1</h3>
              <p>Motion-tracking reinforcement learning</p>
              <dl>
                <dt>Parallel environments</dt>
                <dd>{envs.toLocaleString()}</dd>
                <dt>Iterations</dt>
                <dd>{iterations.toLocaleString()}</dd>
                <dt>Compute placement</dt>
                <dd>Automatic</dd>
                <dt>Source snapshot</dt>
                <dd>
                  Included <Check size={14} />
                </dd>
              </dl>
            </div>
            <div className="tip">
              <Zap size={20} />
              <div>
                <b>Start small, learn faster.</b>
                <p>
                  A short run with 512 environments is a good way to explore
                  your first changes.
                </p>
              </div>
            </div>
          </aside>
        </form>
      )}
    </>
  );
}

function Chart({ metrics = [] }: { metrics?: any[] }) {
  const data = metrics.filter((m) => Number.isFinite(m.reward));
  if (data.length < 2)
    return (
      <div className="chart-empty">
        <Activity size={28} />
        <p>Reward metrics will appear as training progresses.</p>
      </div>
    );
  const values = data.map((m) => m.reward);
  const lo = Math.min(...values),
    hi = Math.max(...values);
  const w = 700,
    h = 210;
  const points = data.map(
    (v, i) =>
      `${45 + (i * (w - 65)) / (data.length - 1)},${h - 30 - ((v.reward - lo) / (hi - lo || 1)) * (h - 55)}`,
  );
  return (
    <svg
      className="chart"
      viewBox={`0 0 ${w} ${h}`}
      role="img"
      aria-label="Training mean reward over iterations"
    >
      <defs>
        <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
          <stop stopColor="#75ac80" stopOpacity=".24" />
          <stop offset="1" stopColor="#75ac80" stopOpacity="0" />
        </linearGradient>
      </defs>
      {[0, 0.5, 1].map((v) => (
        <g key={v}>
          <line
            x1="45"
            x2={w - 20}
            y1={25 + v * (h - 55)}
            y2={25 + v * (h - 55)}
            stroke="#e5e9e2"
            strokeDasharray="4 4"
          />
          <text x="2" y={29 + v * (h - 55)}>
            {(hi - v * (hi - lo)).toFixed(1)}
          </text>
        </g>
      ))}
      <path
        d={`M${points[0].split(",")[0]},${h - 30} L${points.join(" L")} L${w - 20},${h - 30} Z`}
        fill="url(#fill)"
      />
      <polyline
        points={points.join(" ")}
        fill="none"
        stroke="#45825a"
        strokeWidth="2.5"
      />
      <text x="45" y={h - 5}>
        Iteration {data[0].step}
      </text>
      <text x={w - 100} y={h - 5}>
        {data.at(-1).step}
      </text>
    </svg>
  );
}
function RunPage() {
  const { id } = useParams();
  const { user } = useContext(Auth);
  const { data: r, error } = usePoll<Run>(() => api("/runs/" + id), [id]);
  const { data: logs } = usePoll<any>(() => api("/runs/" + id + "/logs"), [id]);
  const action = useAction();
  const [tab, setTab] = useState("overview");
  const [priority, setPriority] = useState(0);
  return (
    <>
      {r ? (
        <>
          <PageHead
            eyebrow={"EXPERIMENT / " + r.id.slice(0, 8)}
            title={r.name}
            description={`${r.spec.task} · ${r.spec.motion.label}`}
            action={
              <div className="actions">
                <Link className="button secondary" to={"/runs/" + id + "/code"}>
                  <Code2 size={16} />
                  View training code
                </Link>
                {active(r) && (
                  <Button
                    variant="danger"
                    disabled={action.busy || !!r.cancel}
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
                    <RefreshCw size={16} />
                    Retry
                  </Button>
                )}
              </div>
            }
          />
          <ErrorBox error={error || action.error} />
          {r.execution?.mock && (
            <div className="warning">
              <FlaskConical size={18} />
              Simulated demonstration. Metrics and checkpoints are synthetic,
              not a trained robot policy.
            </div>
          )}
          {r.worker_online === false && active(r) && (
            <div className="warning">
              <AlertCircle size={18} />
              Worker disconnected. This run retains its allocation and will not
              be retried automatically.
            </div>
          )}
          {r.quarantined && (
            <div className="error">
              Server quarantined. An administrator must reconcile the existing
              processes.
            </div>
          )}
          {r.error && <div className="error">{r.error}</div>}
          <div className="run-status panel">
            <div>
              <Badge status={r.status} />
              <span>
                {r.queue_position
                  ? `Position ${r.queue_position} in the queue`
                  : r.server_name || "Waiting for automatic placement"}
              </span>
            </div>
            <span className="muted">
              {r.email} · Created {date(r.created)}
            </span>
          </div>
          <div className="stats four">
            <Stat
              label="Iteration"
              value={
                <>
                  {r.iteration.toLocaleString()}
                  <em> / {r.spec.iterations.toLocaleString()}</em>
                </>
              }
              icon={Activity}
            />
            <Stat label="Elapsed" value={duration(r)} icon={Clock} />
            <Stat
              label="Environments"
              value={r.spec.num_envs.toLocaleString()}
              icon={Layers}
            />
            <Stat
              label="GPU memory"
              value={r.gpu_mb ? `${(r.gpu_mb / 1024).toFixed(1)} GiB` : "—"}
              detail={
                r.execution?.mps
                  ? "MPS client enabled"
                  : "Reported process allocation"
              }
              icon={Cpu}
            />
          </div>
          <div className="tabs">
            <button
              className={tab === "overview" ? "selected" : ""}
              onClick={() => setTab("overview")}
            >
              Overview & metrics
            </button>
            <button
              className={tab === "logs" ? "selected" : ""}
              onClick={() => setTab("logs")}
            >
              Live logs
            </button>
            <button
              className={tab === "artifacts" ? "selected" : ""}
              onClick={() => setTab("artifacts")}
            >
              Results & checkpoints <span>{r.artifacts?.length || 0}</span>
            </button>
            <Link to={"/runs/" + id + "/code"}>
              Code <ArrowUpRight size={14} />
            </Link>
          </div>
          {tab === "overview" && (
            <>
              <section className="panel">
                <div className="section-title">
                  <div>
                    <h2>Learning progress</h2>
                    <p>Mean reward · locally collected training metrics</p>
                  </div>
                  <span className="live-label">
                    <i className="online-dot" />
                    Updates every 3 seconds
                  </span>
                </div>
                <Chart metrics={r.metrics} />
                <div className="chart-footer">
                  <span>Iteration progress</span>
                  <b>{Math.round((r.iteration / r.spec.iterations) * 100)}%</b>
                  <progress value={r.iteration} max={r.spec.iterations} />
                </div>
              </section>
              <div className="two-col">
                <section className="panel details">
                  <h3>Training configuration</h3>
                  <dl>
                    <dt>Motion artifact</dt>
                    <dd className="mono">{r.spec.motion.artifact}</dd>
                    <dt>Seed</dt>
                    <dd>{r.spec.seed}</dd>
                    <dt>Learning rate</dt>
                    <dd>{r.spec.learning_rate ?? "Task default"}</dd>
                    <dt>Reward overrides</dt>
                    <dd>
                      {Object.entries(r.spec.rewards)
                        .map(([k, v]) => `${k}: ${v}`)
                        .join(", ") || "Task defaults"}
                    </dd>
                  </dl>
                </section>
                <section className="panel details">
                  <h3>Compute & reproducibility</h3>
                  <dl>
                    <dt>Assigned server</dt>
                    <dd>{r.server_name || "Automatic · pending"}</dd>
                    <dt>GPU</dt>
                    <dd className="mono">{r.gpu || "Pending"}</dd>
                    <dt>Execution</dt>
                    <dd>
                      {r.execution?.mock
                        ? "Mock worker"
                        : r.execution?.mps
                          ? "CUDA MPS"
                          : "Standard CUDA"}
                    </dd>
                    <dt>Source</dt>
                    <dd>
                      <Link to={"/runs/" + id + "/code"}>
                        Immutable source snapshot <ArrowUpRight size={13} />
                      </Link>
                    </dd>
                  </dl>
                </section>
              </div>
              {user?.role === "admin" && r.status === "QUEUED" && (
                <section className="panel details">
                  <h3>Queue priority</h3>
                  <p>
                    Higher values run first; waiting time increases priority
                    automatically.
                  </p>
                  <div className="inline-form">
                    <input
                      aria-label="Queue priority"
                      type="number"
                      min={-100}
                      max={100}
                      value={priority}
                      onChange={(e) => setPriority(Number(e.target.value))}
                    />
                    <Button
                      disabled={action.busy}
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
                <h2>Training output</h2>
                <a
                  className="button secondary"
                  href={"/api/runs/" + id + "/logs/download"}
                >
                  <Download size={15} />
                  Download logs
                </a>
              </div>
              <pre className="terminal">
                {logs?.text || "Waiting for worker output…"}
              </pre>
            </section>
          )}
          {tab === "artifacts" && (
            <section className="panel">
              <div className="section-title">
                <div>
                  <h2>Run artifacts</h2>
                  <p>
                    Checkpoints, resolved configuration, and execution metadata.
                  </p>
                </div>
                <a
                  href={"/api/code/" + id + "/download"}
                  className="button secondary"
                >
                  <Download size={15} />
                  Source ZIP
                </a>
              </div>
              {r.artifacts?.length ? (
                <div className="artifact-list">
                  {r.artifacts.map((a) => (
                    <a
                      key={a.path}
                      href={
                        "/api/runs/" +
                        id +
                        "/artifacts?path=" +
                        encodeURIComponent(a.path)
                      }
                    >
                      <span className="resource-icon">
                        <Download size={18} />
                      </span>
                      <div>
                        <b>{a.path}</b>
                        <small>
                          {(a.size / 1024).toFixed(1)} KiB · SHA256{" "}
                          {a.sha256.slice(0, 16)}
                        </small>
                      </div>
                      <Download size={17} />
                    </a>
                  ))}
                </div>
              ) : (
                <Empty title="No artifacts published yet">
                  <p>Artifacts are uploaded when the run finishes or stops.</p>
                </Empty>
              )}
            </section>
          )}
        </>
      ) : (
        <>
          <ErrorBox error={error} />
          <p className="loading">Loading experiment…</p>
        </>
      )}
    </>
  );
}

function CodePage() {
  const { id } = useParams();
  const key = id || "base";
  const { data: run } = usePoll<Run | null>(
    () => (id ? api("/runs/" + id) : Promise.resolve(null)),
    [id],
    10000,
  );
  const { data, error } = usePoll<any>(
    () => api("/code/" + key + "/tree"),
    [key],
    30000,
  );
  const [file, setFile] = useState("");
  const [search, setSearch] = useState("");
  const [content, setContent] = useState<{ content: string; sha256: string }>();
  const [fileError, setFileError] = useState("");
  const notify = useContext(Notice);
  useEffect(() => {
    if (data && !file)
      setFile(
        data.files.find((p: string) =>
          p.endsWith("tracking/config/k1/env_cfgs.py"),
        ) || "hub_launch.py",
      );
  }, [data]);
  useEffect(() => {
    if (file) {
      setContent(undefined);
      setFileError("");
      api("/code/" + key + "/file?path=" + encodeURIComponent(file))
        .then(setContent)
        .catch((e) => setFileError(e.message));
    }
  }, [file, key]);
  const highlight = content ? hljs.highlightAuto(content.content).value : "";
  return (
    <>
      <PageHead
        eyebrow={id ? "EXACT RUN SOURCE" : "WORKSHOP SOURCE"}
        title={id ? "The code behind this run." : "Learn what makes it move."}
        description={
          id
            ? "Read-only, hashed source used to execute this experiment."
            : "Explore the Booster K1 task, rewards, and training infrastructure before your first experiment."
        }
        action={
          <a
            href={"/api/code/" + key + "/download"}
            className="button secondary"
          >
            <Download size={16} />
            Download source ZIP
          </a>
        }
      />
      <ErrorBox error={error} />
      {data && (
        <>
          <div className="source-meta panel">
            <span>
              <ShieldCheck size={17} />
              Frozen source snapshot
            </span>
            {Object.entries(data.manifest.commits).map(([k, v]: any) => (
              <span key={k}>
                {k} <code>{v.slice(0, 12)}</code>
              </span>
            ))}
          </div>
          <div className="code-shortcuts">
            {[
              [
                "Robot task",
                "booster_mjlab/src/booster_mjlab/tasks/tracking/config/k1/env_cfgs.py",
              ],
              [
                "Reward functions",
                "mjlab/src/mjlab/tasks/tracking/mdp/rewards.py",
              ],
              [
                "Training config",
                "booster_mjlab/src/booster_mjlab/tasks/tracking/config/k1/rl_cfg.py",
              ],
              ["Run config", "hub_config.json"],
              ["Launch code", "hub_launch.py"],
              ["Dependencies", "booster_mjlab/uv.lock"],
            ].map(([label, path]) => (
              <button
                key={label}
                onClick={() => setFile(path)}
                className={file === path ? "selected" : ""}
              >
                {label}
              </button>
            ))}
          </div>
          <section className="code-explorer">
            <aside>
              <div className="code-tree-head">
                <Code2 size={16} />
                SOURCE EXPLORER
              </div>
              <div className="search">
                <Search size={15} />
                <input
                  aria-label="Find source file"
                  placeholder="Find a file…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>
              <div className="file-tree">
                {data.files
                  .filter((p: string) =>
                    p.toLowerCase().includes(search.toLowerCase()),
                  )
                  .map((p: string) => (
                    <button
                      className={p === file ? "selected" : ""}
                      key={p}
                      title={p}
                      onClick={() => setFile(p)}
                    >
                      <span>{p.split("/").slice(0, -1).join("/")}/</span>
                      <b>{p.split("/").at(-1)}</b>
                    </button>
                  ))}
              </div>
            </aside>
            <div className="code-main">
              <div className="code-toolbar">
                <span className="mono">{file}</span>
                <button
                  disabled={!content}
                  onClick={async () => {
                    await navigator.clipboard.writeText(content!.content);
                    notify("File copied");
                  }}
                >
                  <Copy size={15} />
                  Copy file
                </button>
              </div>
              <ErrorBox error={fileError} />
              {content ? (
                <pre className="code-view">
                  <code dangerouslySetInnerHTML={{ __html: highlight }} />
                </pre>
              ) : (
                <p className="loading">
                  {fileError
                    ? "Select a text file to continue."
                    : "Loading source…"}
                </p>
              )}
              <div className="code-hash mono">
                SHA256 {content?.sha256 || "—"}
              </div>
            </div>
          </section>
          {id && (
            <section className="panel details">
              <h3>Exact launch and resolved configuration</h3>
              <p>
                The saved <Link to={"/runs/" + id}>run artifacts</Link> include
                execution.json with the actual argument list, source path,
                interpreter, MPS environment, resolved mjlab YAML, dependency
                versions, and motion checksum.
              </p>
              <pre className="inline-code">
                {run?.execution?.argv
                  ? JSON.stringify(run.execution.argv, null, 2)
                  : "Awaiting worker launch. Frozen entrypoint: hub_launch.py"}
              </pre>
            </section>
          )}
        </>
      )}
    </>
  );
}

function AdminRoutes() {
  return (
    <Routes>
      <Route index element={<AdminOverview />} />
      <Route path="runs" element={<RunsPage admin />} />
      <Route path="servers" element={<Servers />} />
      <Route path="users" element={<Participants />} />
      <Route path="settings" element={<WorkshopSettings />} />
    </Routes>
  );
}
function AdminOverview() {
  const { data, error } = usePoll<any>(() => api("/admin/overview"));
  const { data: servers } = usePoll<any[]>(() => api("/admin/servers"));
  const { data: runs } = usePoll<Run[]>(() => api("/runs"));
  const action = useAction();
  const gpus =
    servers?.flatMap((s) => (s.online ? s.inventory.gpus || [] : [])) || [];
  const total = gpus.reduce((a, g) => a + g.total_mb, 0),
    used = gpus.reduce((a, g) => a + g.total_mb - g.free_mb, 0);
  return (
    <>
      <PageHead
        eyebrow="WORKSHOP CONTROL ROOM"
        title="Keep the workshop moving."
        description="One queue. Shared compute. A clear view of every experiment."
        action={
          data && (
            <Button
              variant="secondary"
              disabled={action.busy}
              onClick={() =>
                action.run(
                  () =>
                    api("/admin/settings", "PUT", {
                      ...data.settings,
                      paused: !data.settings.paused,
                    }),
                  data.settings.paused
                    ? "Scheduling resumed"
                    : "Scheduling paused",
                )
              }
            >
              {data.settings.paused ? <Play size={16} /> : <Pause size={16} />}{" "}
              {data.settings.paused ? "Resume queue" : "Pause queue"}
            </Button>
          )
        }
      />
      <ErrorBox error={error || action.error} />
      {data?.settings.paused && (
        <div className="warning">
          <Pause size={18} />
          Scheduling paused. Existing runs continue; new jobs stay queued.
        </div>
      )}
      <div className="stats four">
        <Stat
          label="Participants"
          value={data?.participants ?? "—"}
          icon={Users}
          detail="Registered workshop accounts"
        />
        <Stat
          label="Running / starting"
          value={(data?.jobs.RUNNING || 0) + (data?.jobs.STARTING || 0)}
          icon={Activity}
          detail={`${data?.jobs.QUEUED || 0} experiments queued`}
        />
        <Stat
          label="Completed / failed"
          value={`${data?.jobs.COMPLETED || 0} / ${data?.jobs.FAILED || 0}`}
          icon={Check}
          detail="All workshop experiments"
        />
        <Stat
          label="GPU memory used"
          value={total ? `${(used / 1024).toFixed(1)} GiB` : "—"}
          icon={Cpu}
          detail={`${(total / 1024).toFixed(1)} GiB across online workers · ${gpus.length ? Math.round(gpus.reduce((a, g) => a + g.utilization, 0) / gpus.length) : 0}% avg utilization`}
        />
      </div>
      <div className="section-title outside">
        <div>
          <h2>Workshop compute</h2>
          <p>Live hardware discovery and reserved capacity.</p>
        </div>
        <Link to="/admin/servers" className="text-link">
          Manage compute <ArrowRight size={15} />
        </Link>
      </div>
      <div className="server-grid">
        {servers?.map((s) => (
          <ServerCard key={s.id} server={s} />
        ))}
      </div>
      <section className="panel">
        <div className="section-title">
          <div>
            <h2>Workshop activity</h2>
            <p>Latest experiments from every participant.</p>
          </div>
          <Link to="/admin/runs" className="text-link">
            View all <ArrowRight size={15} />
          </Link>
        </div>
        {runs && <RunTable runs={runs.slice(0, 6)} admin />}
      </section>
      <section className="panel details">
        <h3>Operational audit</h3>
        <div className="audit-list">
          {data?.audit.slice(0, 8).map((a: any) => (
            <div key={a.id}>
              <span className="mono">{date(a.at)}</span>
              <b>{a.action}</b>
              <span className="muted">{a.actor.slice(0, 14)}</span>
            </div>
          ))}
        </div>
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
    <div className="server-card">
      <div className="server-card-head">
        <span className="server-icon">
          <Server size={20} />
        </span>
        <div>
          <h3>{s.name}</h3>
          <small>{s.inventory.hostname || "Awaiting first heartbeat"}</small>
        </div>
        <Badge
          status={
            s.quarantined ? "QUARANTINED" : s.online ? "ONLINE" : "OFFLINE"
          }
        />
      </div>
      {(s.inventory.gpus || []).map((g: any) => {
        const limits = { ...s.config, ...s.config.gpu_limits?.[g.uuid] };
        return (
          <div className="gpu" key={g.uuid}>
            <div className="gpu-label">
              <b>{g.name}</b>
              <span>{g.utilization}% util.</span>
            </div>
            <progress max={g.total_mb} value={g.total_mb - g.free_mb} />
            <div className="gpu-memory">
              <span>
                {((g.total_mb - g.free_mb) / 1024).toFixed(1)} /{" "}
                {(g.total_mb / 1024).toFixed(1)} GiB
              </span>
              <span>{(limits.reserve_mb / 1024).toFixed(0)} GiB reserved</span>
            </div>
            <small className="mono gpu-uuid">{g.uuid}</small>
          </div>
        );
      })}
      {!s.inventory.gpus?.length && (
        <div className="gpu muted">No hardware reported</div>
      )}
      <div className="server-info">
        <span>
          <Layers size={14} />
          {s.active_jobs} active · max {s.config.max_jobs}/GPU
        </span>
        <span className={s.inventory.mps?.ready ? "mps-on" : ""}>
          <Zap size={14} />
          MPS{" "}
          {s.inventory.mps?.ready
            ? "ready"
            : s.config.mps_enabled
              ? "unavailable"
              : "off"}
        </span>
      </div>
      {s.inventory.mock && <div className="mock-label">SIMULATED WORKER</div>}
      <div className="server-card-foot">
        <span>
          <i className={"online-dot " + (!s.config.enabled ? "gray" : "")} />
          {s.config.enabled ? "Accepting jobs" : "New jobs disabled"}
        </span>
        {onEdit && (
          <button onClick={onEdit}>
            Configure <Settings2 size={14} />
          </button>
        )}
      </div>
    </div>
  );
}
function Field({
  label,
  value,
  onChange,
  type = "number",
  min = 0,
  max = 1000000,
  step = "1",
}: {
  label: string;
  value: any;
  onChange: (v: any) => void;
  type?: string;
  min?: number;
  max?: number;
  step?: string;
}) {
  return (
    <label>
      {label}
      <input
        type={type}
        value={value ?? ""}
        min={min}
        max={max}
        step={step}
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
  detail,
}: {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
  detail?: string;
}) {
  return (
    <label className="toggle-row">
      <span>
        <b>{label}</b>
        {detail && <small>{detail}</small>}
      </span>
      <input
        type="checkbox"
        checked={value}
        onChange={(e) => onChange(e.target.checked)}
      />
    </label>
  );
}
const defaultServer = {
  enabled: true,
  max_envs: 4096,
  max_jobs: 1,
  reserve_mb: 46080,
  margin_mb: 2048,
  mode: "direct",
  institutional_permission: false,
  mps_enabled: false,
  mps_required: false,
  mps_kind: "legacy",
  mps_pipe: "",
  mps_log: "",
  mps_threads: 50,
  mps_memory_mb: 0,
  mps_namespace: "",
  mps_server: "",
  gpu_limits: {},
};
function Servers() {
  const { data, error } = usePoll<any[]>(() => api("/admin/servers"));
  const [editing, setEditing] = useState<any>();
  const [config, setConfig] = useState<any>();
  const [name, setName] = useState("");
  const [token, setToken] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const action = useAction();
  const update = (k: string, v: any) => setConfig({ ...config, [k]: v });
  return (
    <>
      <PageHead
        eyebrow="COMPUTE INFRASTRUCTURE"
        title="A home for every experiment."
        description="Configure GPU capacity, resource reservations, and CUDA MPS per host."
        action={
          <Button
            onClick={() => {
              setEditing({ new: true });
              setConfig({ ...defaultServer });
              setName("");
            }}
          >
            <Plus size={16} />
            Add server
          </Button>
        }
      />
      <ErrorBox error={error || action.error} />
      {token && (
        <section className="panel details">
          <h3>Worker enrollment token</h3>
          <p>Save this securely on the host. It is shown only once.</p>
          <div className="token-row">
            <code>{token}</code>
            <Button
              variant="secondary"
              onClick={() => navigator.clipboard.writeText(token)}
            >
              <Copy size={15} />
            </Button>
            <Button variant="secondary" onClick={() => setToken("")}>
              Dismiss
            </Button>
          </div>
        </section>
      )}
      <div className="server-grid">
        {data?.map((s) => (
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
      <section className="panel details">
        <h3>Capacity is reserved before launch</h3>
        <p>
          The scheduler accounts for observed external memory, workshop
          reservations, memory margins, environment limits, and per-GPU
          concurrency. Disconnected jobs retain their allocations. Shared H100
          hosts default to reserving 45 GiB for other researchers.
        </p>
      </section>
      {editing && config && (
        <div className="modal-backdrop">
          <section className="modal">
            <div className="section-title">
              <div>
                <div className="eyebrow">SERVER CONFIGURATION</div>
                <h2>{editing.new ? "Enroll a new worker" : editing.name}</h2>
              </div>
              <button
                aria-label="Close server configuration"
                onClick={() => setEditing(undefined)}
              >
                <X />
              </button>
            </div>
            <div className="modal-content">
              {editing.new && (
                <Field
                  label="Server name"
                  type="text"
                  value={name}
                  onChange={setName}
                />
              )}
              <Toggle
                label="Accept new jobs"
                value={config.enabled}
                onChange={(v) => update("enabled", v)}
              />
              <Toggle
                label="Host owner permits workshop training"
                detail="Confirm university policy and allocation before enabling placement."
                value={config.institutional_permission}
                onChange={(v) => update("institutional_permission", v)}
              />
              <label>
                Host allocation mode
                <select
                  value={config.mode}
                  onChange={(e) => update("mode", e.target.value)}
                >
                  <option value="direct">Direct · owner-authorized host</option>
                  <option value="slurm">
                    Slurm · worker inside allocated job
                  </option>
                </select>
              </label>
              <h3>Default GPU limits</h3>
              <div className="form-grid">
                <Field
                  label="Concurrent jobs per GPU"
                  value={config.max_jobs}
                  onChange={(v) => update("max_jobs", v)}
                  min={1}
                  max={18}
                />
                <Field
                  label="Maximum environments per job"
                  value={config.max_envs}
                  onChange={(v) => update("max_envs", v)}
                  min={1}
                  max={16384}
                />
                <Field
                  label="Reserved for others (MiB)"
                  value={config.reserve_mb}
                  onChange={(v) => update("reserve_mb", v)}
                />
                <Field
                  label="Memory safety margin (MiB)"
                  value={config.margin_mb}
                  onChange={(v) => update("margin_mb", v)}
                  min={256}
                />
              </div>
              {editing.inventory?.gpus?.map((g: any) => (
                <div className="gpu-override" key={g.uuid}>
                  <h4>
                    {g.name} <small>{g.uuid.slice(0, 18)}</small>
                  </h4>
                  <Toggle
                    label="Use per-GPU overrides"
                    value={!!config.gpu_limits?.[g.uuid]}
                    onChange={(v) => {
                      const limits = { ...config.gpu_limits };
                      if (v)
                        limits[g.uuid] = {
                          max_jobs: config.max_jobs,
                          max_envs: config.max_envs,
                          reserve_mb: config.reserve_mb,
                          margin_mb: config.margin_mb,
                        };
                      else delete limits[g.uuid];
                      update("gpu_limits", limits);
                    }}
                  />
                  {config.gpu_limits?.[g.uuid] && (
                    <div className="form-grid">
                      {[
                        ["max_jobs", "Concurrent jobs"],
                        ["max_envs", "Maximum environments"],
                        ["reserve_mb", "Reserved MiB"],
                        ["margin_mb", "Margin MiB"],
                      ].map(([k, label]) => (
                        <Field
                          key={k}
                          label={label}
                          value={config.gpu_limits[g.uuid][k]}
                          onChange={(v) =>
                            update("gpu_limits", {
                              ...config.gpu_limits,
                              [g.uuid]: {
                                ...config.gpu_limits[g.uuid],
                                [k]: v,
                              },
                            })
                          }
                        />
                      ))}
                    </div>
                  )}
                </div>
              ))}
              <h3>CUDA Multi-Process Service</h3>
              <p className="muted">
                Attach to an existing, explicitly provisioned MPS service. No
                global compute mode or daemon is changed.
              </p>
              <Toggle
                label="Enable MPS clients"
                value={config.mps_enabled}
                onChange={(v) => update("mps_enabled", v)}
              />
              {config.mps_enabled && (
                <>
                  <Toggle
                    label="Require MPS; otherwise keep jobs queued"
                    value={config.mps_required}
                    onChange={(v) => update("mps_required", v)}
                  />
                  <label>
                    MPS interface
                    <select
                      value={config.mps_kind}
                      onChange={(e) => update("mps_kind", e.target.value)}
                    >
                      <option value="legacy">Legacy MPS v2</option>
                      <option value="v3">MPS v3</option>
                    </select>
                  </label>
                  <Field
                    label="MPS pipe directory (absolute)"
                    type="text"
                    value={config.mps_pipe}
                    onChange={(v) => update("mps_pipe", v)}
                  />
                  <Field
                    label="MPS log directory (absolute)"
                    type="text"
                    value={config.mps_log}
                    onChange={(v) => update("mps_log", v)}
                  />
                  <div className="form-grid">
                    <Field
                      label="Active thread percentage"
                      value={config.mps_threads}
                      onChange={(v) => update("mps_threads", v)}
                      min={1}
                      max={100}
                    />
                    <Field
                      label="Pinned device memory limit (MiB; 0 = unset)"
                      value={config.mps_memory_mb}
                      onChange={(v) => update("mps_memory_mb", v)}
                    />
                  </div>
                  {config.mps_kind === "v3" && (
                    <>
                      <Field
                        label="MPS v3 named server (site-provisioned)"
                        type="text"
                        value={config.mps_server || ""}
                        onChange={(v) => update("mps_server", v)}
                      />
                      <Field
                        label="MPS v3 namespace (site-provisioned)"
                        type="text"
                        value={config.mps_namespace}
                        onChange={(v) => update("mps_namespace", v)}
                      />
                    </>
                  )}
                  <div className="info">
                    {editing.inventory?.mps?.reason ||
                      "Worker will report MPS readiness on its next heartbeat."}
                  </div>
                </>
              )}
              {editing.quarantined && (
                <div className="reconcile">
                  <h3>Reconcile interrupted worker</h3>
                  <p>
                    Check this host and stop all old workshop processes before
                    releasing their allocations.
                  </p>
                  <Toggle
                    label="I verified all old workshop processes have stopped"
                    value={confirmed}
                    onChange={setConfirmed}
                  />
                  <Button
                    variant="danger"
                    disabled={!confirmed || action.busy}
                    onClick={() =>
                      action.run(async () => {
                        await api(
                          "/admin/servers/" + editing.id + "/reconcile",
                          "POST",
                          { confirmed_all_processes_stopped: true },
                        );
                        setEditing(undefined);
                      }, "Worker reconciled")
                    }
                  >
                    Confirm stopped and release allocations
                  </Button>
                </div>
              )}
              <ErrorBox error={action.error} />
            </div>
            <div className="modal-footer">
              <span>Changes apply to future admissions.</span>
              <Button
                disabled={action.busy}
                onClick={() =>
                  action.run(async () => {
                    if (editing.new) {
                      const r = await api("/admin/servers", "POST", {
                        name,
                        config,
                      });
                      setToken(r.token);
                    } else
                      await api("/admin/servers/" + editing.id, "PUT", config);
                    setEditing(undefined);
                  })
                }
              >
                Save configuration
              </Button>
            </div>
          </section>
        </div>
      )}
    </>
  );
}

function Participants() {
  const { data, error } = usePoll<User[]>(() => api("/admin/users"));
  const [email, setEmail] = useState("");
  const [q, setQ] = useState("");
  const action = useAction();
  const [edit, setEdit] = useState<User>();
  const filtered =
    data?.filter((u) => u.email.toLowerCase().includes(q.toLowerCase())) || [];
  return (
    <>
      <PageHead
        eyebrow="WORKSHOP COMMUNITY"
        title="Everyone starts somewhere."
        description="Approve attendee emails, manage roles, and set individual environment limits."
      />
      <ErrorBox error={error || action.error} />
      <section className="panel details">
        <h3>Add an approved attendee</h3>
        <form
          className="inline-form"
          onSubmit={(e) => {
            e.preventDefault();
            action.run(async () => {
              await api("/admin/users", "POST", { email });
              setEmail("");
            }, "Attendee approved");
          }}
        >
          <input
            aria-label="Attendee email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="participant@university.edu"
          />
          <Button type="submit" disabled={action.busy}>
            <Plus size={16} />
            Approve email
          </Button>
        </form>
      </section>
      <section className="panel">
        <div className="filterbar">
          <div className="search">
            <Search size={17} />
            <input
              aria-label="Search participants"
              placeholder="Search participants…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
          <span>{filtered.length} accounts</span>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Participant</th>
                <th>Role</th>
                <th>Access</th>
                <th>Email</th>
                <th>Environment limit</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {filtered.map((u) => (
                <tr key={u.id}>
                  <td>
                    <b>{u.email}</b>
                    <small>Joined {date((u as any).created)}</small>
                  </td>
                  <td>{u.role}</td>
                  <td>
                    <Badge status={u.approved ? "APPROVED" : "PENDING"} />
                  </td>
                  <td>{u.verified ? "Verified" : "Unverified"}</td>
                  <td>{u.env_limit || "Workshop default"}</td>
                  <td>
                    <Button
                      variant="secondary small"
                      onClick={() => setEdit({ ...u })}
                    >
                      Manage
                    </Button>
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
              <h2>Manage attendee</h2>
              <button
                onClick={() => setEdit(undefined)}
                aria-label="Close attendee"
              >
                <X />
              </button>
            </div>
            <div className="modal-content">
              <p>{edit.email}</p>
              <Toggle
                label="Approved for workshop access"
                value={!!edit.approved}
                onChange={(v) => setEdit({ ...edit, approved: v })}
              />
              <label>
                Role
                <select
                  value={edit.role}
                  onChange={(e) => setEdit({ ...edit, role: e.target.value })}
                >
                  <option value="participant">Participant</option>
                  <option value="admin">Administrator</option>
                </select>
              </label>
              <label>
                Maximum environments (optional)
                <input
                  type="number"
                  min={1}
                  max={16384}
                  placeholder="Workshop default"
                  value={edit.env_limit ?? ""}
                  onChange={(e) =>
                    setEdit({
                      ...edit,
                      env_limit: e.target.value ? Number(e.target.value) : null,
                    })
                  }
                />
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
                Save attendee
              </Button>
            </div>
          </section>
        </div>
      )}
    </>
  );
}
function WorkshopSettings() {
  const { data, error } = usePoll<any>(() => api("/admin/settings"), [], 20000);
  const [form, setForm] = useState<any>();
  const [motionText, setMotionText] = useState("");
  const action = useAction();
  useEffect(() => {
    if (data && !form) {
      setForm(structuredClone(data));
      setMotionText(JSON.stringify(data.motions, null, 2));
    }
  }, [data]);
  const update = (k: string, v: any) => setForm({ ...form, [k]: v });
  return (
    <>
      <PageHead
        eyebrow="WORKSHOP CONFIGURATION"
        title="Set the boundaries for discovery."
        description="Control participant budgets and approved training parameters without changing source code."
      />
      <ErrorBox error={error || action.error} />
      {form && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            action.run(
              () =>
                api("/admin/settings", "PUT", {
                  ...form,
                  motions: JSON.parse(motionText),
                }),
              "Workshop settings saved",
            );
          }}
        >
          <section className="panel details">
            <h2>Parallel environment limits</h2>
            <p className="muted">
              These limits apply to future submissions. Existing runs keep their
              saved configuration.
            </p>
            <div className="form-grid">
              <Field
                label="Default environments"
                value={form.default_envs}
                min={1}
                max={16384}
                onChange={(v) => update("default_envs", v)}
              />
              <Field
                label="Minimum environments"
                value={form.min_envs}
                min={1}
                max={16384}
                onChange={(v) => update("min_envs", v)}
              />
              <Field
                label="Maximum environments"
                value={form.max_envs}
                min={1}
                max={16384}
                onChange={(v) => update("max_envs", v)}
              />
              <Field
                label="Maximum iterations"
                value={form.max_iterations}
                min={1}
                max={100000}
                onChange={(v) => update("max_iterations", v)}
              />
            </div>
            <label>
              Allowed environment presets (comma separated)
              <input
                defaultValue={form.presets.join(", ")}
                onChange={(e) =>
                  update(
                    "presets",
                    e.target.value.split(",").map((n) => Number(n.trim())),
                  )
                }
              />
            </label>
            <Toggle
              label="Pause automatic scheduling"
              detail="Running experiments continue; submissions remain in the queue."
              value={form.paused}
              onChange={(v) => update("paused", v)}
            />
          </section>
          <section className="panel details">
            <h2>Approved motion artifacts</h2>
            <p className="muted">
              Use immutable W&B artifact versions, for example
              organization/motions/walk:v0. Optional SHA256 verifies motion.npz
              before training.
            </p>
            <label>
              Motion catalog (JSON)
              <textarea
                className="json-editor"
                rows={10}
                value={motionText}
                onChange={(e) => setMotionText(e.target.value)}
                spellCheck={false}
              />
            </label>
            <small>
              Each entry: id, label, artifact, and optional sha256. Demo entries
              work only with mock workers.
            </small>
          </section>
          <section className="panel details">
            <h2>Memory estimation profile</h2>
            <p className="muted">
              Estimated MiB = (base + environments × per-environment MiB) ×
              safety factor. Calibrate using the benchmark tool and measured
              training peaks.
            </p>
            <div className="form-grid three">
              {[
                ["base_mb", "Base allocation (MiB)"],
                ["per_env_mb", "Per environment (MiB)"],
                ["safety_factor", "Safety factor"],
              ].map(([k, label]) => (
                <Field
                  key={k}
                  label={label}
                  value={form.memory_profiles[k]}
                  min={k === "safety_factor" ? 1 : 0}
                  step="any"
                  onChange={(v) =>
                    update("memory_profiles", {
                      ...form.memory_profiles,
                      [k]: v,
                    })
                  }
                />
              ))}
            </div>
          </section>
          <section className="panel details">
            <h2>Approved parameter ranges</h2>
            <div className="form-grid">
              <Field
                label="Minimum learning rate"
                value={form.learning_rate_bounds[0]}
                min={0.000001}
                max={0.01}
                step="any"
                onChange={(v) =>
                  update("learning_rate_bounds", [
                    v,
                    form.learning_rate_bounds[1],
                  ])
                }
              />
              <Field
                label="Maximum learning rate"
                value={form.learning_rate_bounds[1]}
                min={0.000001}
                max={0.01}
                step="any"
                onChange={(v) =>
                  update("learning_rate_bounds", [
                    form.learning_rate_bounds[0],
                    v,
                  ])
                }
              />
            </div>
            {Object.entries(form.reward_bounds).map(([key, bounds]: any) => (
              <div className="form-grid" key={key}>
                <Field
                  label={key + " · minimum"}
                  value={bounds[0]}
                  min={-100}
                  step="any"
                  onChange={(v) =>
                    update("reward_bounds", {
                      ...form.reward_bounds,
                      [key]: [v, bounds[1]],
                    })
                  }
                />
                <Field
                  label={key + " · maximum"}
                  value={bounds[1]}
                  min={-100}
                  step="any"
                  onChange={(v) =>
                    update("reward_bounds", {
                      ...form.reward_bounds,
                      [key]: [bounds[0], v],
                    })
                  }
                />
              </div>
            ))}
          </section>
          <div className="savebar">
            <span>
              <ShieldCheck size={16} />
              Settings are validated and recorded in the audit log.
            </span>
            <Button type="submit" disabled={action.busy}>
              {action.busy ? "Saving…" : "Save workshop settings"}
              <Check size={16} />
            </Button>
          </div>
        </form>
      )}
    </>
  );
}

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState("");
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
      const t = setTimeout(() => setNotice(""), 4000);
      return () => clearTimeout(t);
    }
  }, [notice]);
  if (loading)
    return (
      <div className="boot">
        <Cpu />
        <span>Opening your workspace…</span>
      </div>
    );
  return (
    <Auth.Provider value={{ user, reload }}>
      <Notice.Provider value={setNotice}>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Login register />} />
            <Route path="/*" element={<Shell />} />
          </Routes>
        </BrowserRouter>
        {notice && (
          <div role="status" className="toast">
            <Check size={17} />
            {notice}
          </div>
        )}
      </Notice.Provider>
    </Auth.Provider>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
