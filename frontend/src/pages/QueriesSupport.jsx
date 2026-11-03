import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle, AlertTriangle, ArrowLeft, CheckCircle2, Clock3,
  Download, FileText, Filter, LifeBuoy, MessageSquare, Paperclip,
  Plus, RefreshCw, Search, Send, Shield, UserRound,
} from "lucide-react";
import api from "../services/api";
import { isAdministrator } from "../services/auth";
import "./QueriesSupport.css";

const CATEGORIES = [
  ["TECHNICAL_PROBLEM", "Technical Problem"],
  ["SATELLITE_IMAGE_ISSUES", "Satellite Image Issues"],
  ["ANALYSIS_NDVI_ISSUES", "Analysis and NDVI Issues"],
  ["DETECTION_ALERT_ISSUES", "Detection and Alert Issues"],
  ["SMS_NOTIFICATION_ISSUES", "SMS Notification Issues"],
  ["ACCOUNT_LOGIN_ISSUES", "Account and Login Issues"],
  ["DATA_ACCURACY_ISSUES", "Data Accuracy Issues"],
  ["GENERAL_ENQUIRIES", "General Enquiries"],
  ["OTHER", "Other"],
];
const PRIORITIES = ["LOW", "MEDIUM", "HIGH", "URGENT"];
const STATUSES = ["PENDING", "UNDER_REVIEW", "IN_PROGRESS", "RESOLVED"];
const label = (value) => String(value || "").replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
const date = (value) => value ? new Date(value).toLocaleString("en-ZM", { dateStyle: "medium", timeStyle: "short" }) : "—";
const errorText = (error) => error?.response?.data?.detail || error?.message || "Something went wrong. Please try again.";

export default function QueriesSupport({ currentUser, initialQueryId }) {
  const admin = isAdministrator(currentUser);
  const [items, setItems] = useState([]);
  const [stats, setStats] = useState({});
  const [options, setOptions] = useState({ districts: [], officers: [], administrators: [] });
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState({ district_id: "", officer_id: "", category: "", priority: "", status: "" });
  const [form, setForm] = useState({ subject: "", category: "TECHNICAL_PROBLEM", description: "", priority: "MEDIUM", attachments: [] });
  const [reply, setReply] = useState("");
  const [replyFiles, setReplyFiles] = useState([]);
  const [internal, setInternal] = useState(false);
  const [assignment, setAssignment] = useState("");
  const [busy, setBusy] = useState(false);

  const params = useMemo(() => {
    const result = {};
    if (admin && search.trim()) result.search = search.trim();
    if (admin) Object.entries(filters).forEach(([key, value]) => { if (value) result[key] = value; });
    return result;
  }, [admin, search, filters]);

  const loadItems = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await api.get("/support/queries", { params });
      setItems(response.data);
    } catch (e) { setError(errorText(e)); }
    finally { setLoading(false); }
  }, [params]);

  const loadSelected = useCallback(async (queryId) => {
    try {
      const response = await api.get(`/support/queries/${queryId}`);
      setSelected(response.data);
      setAssignment(response.data.assigned_admin_id || "");
    } catch (e) { setError(errorText(e)); }
  }, []);

  useEffect(() => { loadItems(); }, [loadItems]);
  useEffect(() => {
    if (initialQueryId) loadSelected(initialQueryId);
  }, [initialQueryId, loadSelected]);
  useEffect(() => {
    if (!admin) return;
    Promise.all([api.get("/support/queries/stats"), api.get("/support/filters")])
      .then(([statsResponse, optionsResponse]) => {
        setStats(statsResponse.data);
        setOptions(optionsResponse.data);
      })
      .catch((e) => setError(errorText(e)));
  }, [admin]);

  const refresh = async () => {
    await loadItems();
    if (selected) await loadSelected(selected.id);
    if (admin) {
      try { setStats((await api.get("/support/queries/stats")).data); } catch { /* keep current counters */ }
    }
  };

  const submitQuery = async (event) => {
    event.preventDefault();
    setBusy(true); setError(""); setNotice("");
    const body = new FormData();
    body.append("subject", form.subject);
    body.append("category", form.category);
    body.append("description", form.description);
    body.append("priority", form.priority);
    form.attachments.forEach((file) => body.append("attachments", file));
    try {
      const response = await api.post("/support/queries", body, { headers: { "Content-Type": "multipart/form-data" } });
      setForm({ subject: "", category: "TECHNICAL_PROBLEM", description: "", priority: "MEDIUM", attachments: [] });
      setNotice(`Query ${response.data.reference} submitted.`);
      await loadItems();
      setSelected(response.data);
    } catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  };

  const sendReply = async (event) => {
    event.preventDefault();
    if (!selected || (!reply.trim() && replyFiles.length === 0)) return;
    setBusy(true); setError(""); setNotice("");
    const body = new FormData();
    body.append("message", reply.trim() || "Please see the attached file.");
    body.append("internal_note", internal ? "true" : "false");
    replyFiles.forEach((file) => body.append("attachments", file));
    try {
      await api.post(`/support/queries/${selected.id}/messages`, body, { headers: { "Content-Type": "multipart/form-data" } });
      setReply(""); setReplyFiles([]); setInternal(false);
      await loadSelected(selected.id); await loadItems();
      setNotice(internal ? "Internal note added." : "Message sent.");
    } catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  };

  const changeStatus = async (next) => {
    if (!selected) return;
    const body = new FormData(); body.append("new_status", next);
    setBusy(true); setError("");
    try { await api.patch(`/support/queries/${selected.id}/status`, body, { headers: { "Content-Type": "multipart/form-data" } }); await loadSelected(selected.id); await refresh(); }
    catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  };

  const assignQuery = async (event) => {
    event.preventDefault();
    if (!assignment) return;
    const body = new FormData(); body.append("administrator_id", assignment);
    setBusy(true); setError("");
    try { await api.post(`/support/queries/${selected.id}/assign`, body, { headers: { "Content-Type": "multipart/form-data" } }); await loadSelected(selected.id); await refresh(); }
    catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  };

  const download = async (attachment) => {
    try {
      const response = await api.get(`/support/attachments/${attachment.id}/download`, { responseType: "blob" });
      const url = URL.createObjectURL(response.data);
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = attachment.filename;
      document.body.appendChild(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(url);
    } catch (e) { setError(errorText(e)); }
  };

  const files = (attachments = []) => attachments.length > 0 && (
    <div className="support-attachments">
      {attachments.map((file) => <button className="support-attachment" type="button" key={file.id} onClick={() => download(file)}>
        <FileText size={15} /><span>{file.filename}</span><Download size={14} />
      </button>)}
    </div>
  );

  return (
    <section className="support-page">
      <div className="support-heading">
        <div className="support-heading-icon"><LifeBuoy size={24} /></div>
        <div><p className="support-eyebrow">FORESTWATCH HELP DESK</p><h1>Queries &amp; Support</h1>
          <p>{admin ? "Review officer requests, coordinate responses and track resolution." : "Ask for help with ForestWatch or follow up on a previous query."}</p>
        </div>
        <button className="support-refresh" type="button" onClick={refresh} aria-label="Refresh queries"><RefreshCw size={17} /></button>
      </div>

      {error && <div className="support-feedback is-error" role="alert"><AlertCircle size={17} />{error}<button onClick={() => setError("")} aria-label="Dismiss">×</button></div>}
      {notice && <div className="support-feedback is-success" role="status"><CheckCircle2 size={17} />{notice}<button onClick={() => setNotice("")} aria-label="Dismiss">×</button></div>}

      {admin && <div className="support-stats">
        {[["Total queries", stats.total, "total"], ["Pending", stats.pending, "pending"], ["Under review", stats.under_review, "review"], ["In progress", stats.in_progress, "progress"], ["Resolved", stats.resolved, "resolved"], ["Urgent", stats.urgent, "urgent"]].map(([title, value, tone]) =>
          <div className={`support-stat tone-${tone}`} key={title}><span>{title}</span><strong>{value ?? "—"}</strong></div>)}
      </div>}

      {selected ? (
        <div className="support-detail">
          <div className="support-detail-top">
            <button className="support-back" type="button" onClick={() => { setSelected(null); setError(""); }}><ArrowLeft size={16} /> {admin ? "All queries" : "My queries"}</button>
            <div className="support-detail-actions">
              <span className={`support-status status-${selected.status?.toLowerCase()}`}>{label(selected.status)}</span>
              {admin && <select aria-label="Change query status" value={selected.status} disabled={busy} onChange={(e) => changeStatus(e.target.value)}>
                {STATUSES.map((value) => <option key={value} value={value}>{label(value)}</option>)}
              </select>}
            </div>
          </div>
          <div className="support-detail-grid">
            <article className="support-conversation">
              <div className="support-query-title">
                <div className="support-reference">{selected.reference}</div>
                <h2>{selected.subject}</h2>
                <div className="support-query-meta"><span>{label(selected.category)}</span><span className={`support-priority priority-${selected.priority?.toLowerCase()}`}>{label(selected.priority)}</span><span><Clock3 size={14} /> Submitted {date(selected.created_at)}</span></div>
                <p className="support-description">{selected.description}</p>
                {files(selected.attachments)}
              </div>
              <div className="support-thread">
                <h3><MessageSquare size={17} /> Conversation <span>{selected.messages?.length || 0}</span></h3>
                {(selected.messages || []).map((entry) => (
                  <div className={`support-message ${entry.is_internal_note ? "is-internal" : ""}`} key={entry.id}>
                    <div className="support-message-avatar">{entry.is_internal_note ? <Shield size={16} /> : <UserRound size={16} />}</div>
                    <div className="support-message-body">
                      <div className="support-message-heading"><strong>{entry.sender_name}</strong><span>{label(entry.sender_role)}</span>{entry.is_internal_note && <em>Internal note</em>}<time>{date(entry.created_at)}</time></div>
                      <p>{entry.message}</p>{files(entry.attachments)}
                    </div>
                  </div>
                ))}
              </div>
              {selected.status !== "RESOLVED" || admin ? <form className="support-reply" onSubmit={sendReply}>
                {admin && <label className="support-internal-toggle"><input type="checkbox" checked={internal} onChange={(e) => setInternal(e.target.checked)} /> Add internal note (officers cannot see this)</label>}
                <textarea value={reply} onChange={(e) => setReply(e.target.value)} maxLength={10000} placeholder={internal ? "Write an internal administrative note…" : "Write a reply…"} aria-label={internal ? "Internal note" : "Reply"} />
                <div className="support-reply-actions"><label className="support-file-picker"><Paperclip size={16} /> Attach files<input type="file" multiple accept=".pdf,.png,.jpg,.jpeg,.txt,.csv,.docx,.xlsx" onChange={(e) => setReplyFiles(Array.from(e.target.files || []).slice(0, 5))} /></label>
                  <span>{replyFiles.map((f) => f.name).join(", ")}</span><button className="support-primary-button" disabled={busy || (!reply.trim() && replyFiles.length === 0)}><Send size={15} />{internal ? "Add note" : "Send reply"}</button></div>
              </form> : <div className="support-resolved-note"><CheckCircle2 size={17} /> This query is resolved. Contact an administrator if it needs to be reopened.</div>}
            </article>
            <aside className="support-sidebar-card">
              <h3>Query details</h3>
              <Detail label="Reference" value={selected.reference} />
              <Detail label="Submitted by" value={selected.officer_name} />
              <Detail label="District" value={selected.district_name || "Not assigned"} />
              <Detail label="Category" value={label(selected.category)} />
              <Detail label="Priority" value={label(selected.priority)} />
              <Detail label="Last response" value={date(selected.last_response_at)} />
              {admin && <form className="support-assign-form" onSubmit={assignQuery}><label htmlFor="support-assignment">Assigned administrator</label>
                <select id="support-assignment" value={assignment} onChange={(e) => setAssignment(e.target.value)}><option value="">Select administrator</option>{options.administrators.map((person) => <option key={person.id} value={person.id}>{person.name}</option>)}</select>
                <button className="support-secondary-button" disabled={busy || !assignment}><UserRound size={15} /> Assign query</button></form>}
              <div className="support-sidebar-foot"><AlertTriangle size={15} /> Internal notes are restricted to administrators.</div>
            </aside>
          </div>
        </div>
      ) : <div className="support-workspace">
        {!admin && <form className="support-submit-card" onSubmit={submitQuery}>
          <div className="support-section-title"><div><h2>Submit a query</h2><p>Include enough detail for the team to investigate.</p></div><Plus size={19} /></div>
          <div className="support-form-grid">
            <label>Query subject<input required minLength={3} maxLength={200} value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} placeholder="Briefly describe the issue" /></label>
            <label>Query category<select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>{CATEGORIES.map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></label>
            <label>Priority level<select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>{PRIORITIES.map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label>
            <label className="support-description-field">Problem description<textarea required minLength={5} maxLength={10000} rows={5} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Explain what happened, what you expected, and any steps to reproduce it." /></label>
            <label className="support-file-picker"><Paperclip size={16} /> Add attachments (up to 5, 10 MB each)<input type="file" multiple accept=".pdf,.png,.jpg,.jpeg,.txt,.csv,.docx,.xlsx" onChange={(e) => setForm({ ...form, attachments: Array.from(e.target.files || []).slice(0, 5) })} /></label>
            <div className="support-selected-files">{form.attachments.map((f) => <span key={`${f.name}-${f.lastModified}`}>{f.name}</span>)}</div>
          </div>
          <button className="support-primary-button" disabled={busy}><Send size={16} /> {busy ? "Submitting…" : "Submit query"}</button>
        </form>}

        <section className="support-list-panel">
          <div className="support-section-title"><div><h2>{admin ? "Officer queries" : "My queries"}</h2><p>{admin ? "Search, filter and open a request to manage the conversation." : "Your submitted requests and their latest status."}</p></div><span className="support-total-pill">{items.length} {items.length === 1 ? "query" : "queries"}</span></div>
          {admin && <div className="support-filters">
            <label className="support-search"><Search size={16} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search reference, subject or officer" /></label>
            <label><Filter size={15} /><select aria-label="Filter by district" value={filters.district_id} onChange={(e) => setFilters({ ...filters, district_id: e.target.value })}><option value="">All districts</option>{options.districts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
            <select aria-label="Filter by officer" value={filters.officer_id} onChange={(e) => setFilters({ ...filters, officer_id: e.target.value })}><option value="">All officers</option>{options.officers.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</select>
            <select aria-label="Filter by category" value={filters.category} onChange={(e) => setFilters({ ...filters, category: e.target.value })}><option value="">All categories</option>{CATEGORIES.map(([v, text]) => <option key={v} value={v}>{text}</option>)}</select>
            <select aria-label="Filter by priority" value={filters.priority} onChange={(e) => setFilters({ ...filters, priority: e.target.value })}><option value="">All priorities</option>{PRIORITIES.map((v) => <option key={v} value={v}>{label(v)}</option>)}</select>
            <select aria-label="Filter by status" value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}><option value="">All statuses</option>{STATUSES.map((v) => <option key={v} value={v}>{label(v)}</option>)}</select>
          </div>}
          {loading ? <div className="support-empty"><RefreshCw className="support-spin" size={22} /><p>Loading queries…</p></div> : items.length === 0 ? <div className="support-empty"><MessageSquare size={27} /><strong>{admin ? "No matching queries" : "No queries submitted yet"}</strong><p>{admin ? "Try changing the search or filters." : "Use the form above when you need help."}</p></div> :
            <div className="support-query-list">{items.map((item) => <button type="button" className="support-query-row" key={item.id} onClick={() => loadSelected(item.id)}>
              <div className="support-row-icon"><MessageSquare size={18} /></div><div className="support-row-main"><div className="support-row-title"><strong>{item.subject}</strong><span>{item.reference}</span></div><div className="support-row-meta"><span>{admin ? item.officer_name : label(item.category)}</span>{item.district_name ? <span>{item.district_name}</span> : admin ? <span>District not assigned</span> : null}<span>Submitted {date(item.created_at)}</span><span>Last response {date(item.last_response_at)}</span></div></div>
              <span className={`support-priority priority-${item.priority.toLowerCase()}`}>{label(item.priority)}</span><span className={`support-status status-${item.status.toLowerCase()}`}>{label(item.status)}</span>
            </button>)}</div>}
        </section>
      </div>}
    </section>
  );
}

function Detail({ label: title, value }) {
  return <div className="support-detail-item"><span>{title}</span><strong>{value || "—"}</strong></div>;
}
