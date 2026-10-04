const TASK_TYPES = [
  ['cleanup', 'Cleanup'],
  ['repair', 'Repair'],
  ['delivery', 'Delivery'],
  ['assessment', 'Assessment'],
]

export default function CreateTaskForm({ createTask, setShowCreate, activeJobs, form, setForm, board, creating }) {
  return (
    <form className="panel mb-12" onSubmit={createTask}>
      <div className="panel__header">
        <h4>New task</h4>
        <button type="button" className="btn btn--ghost btn--sm" onClick={() => setShowCreate(false)}>
          Close
        </button>
      </div>
      <div className="panel__grid">
        <div className="field">
          <label htmlFor="task-case">Your job</label>
          <select id="task-case" className="input" required value={form.jobId} onChange={(event) => setForm({ ...form, jobId: event.target.value })}>
            <option value="">Choose a job</option>
            {activeJobs.map((item) => <option key={item.id} value={item.id}>#{item.case_reference} · {item.case_village} · {item.help_type_display}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="task-title">Task</label>
          <input id="task-title" className="input" required maxLength="150" placeholder="e.g. Remove damaged furniture" value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="task-type">Type</label>
          <select id="task-type" className="input" value={form.taskType} onChange={(event) => setForm({ ...form, taskType: event.target.value })}>
            {TASK_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="task-lead">Accountable responder</label>
          <select id="task-lead" className="input" value={form.leadId} onChange={(event) => setForm({ ...form, leadId: event.target.value })}>
            <option value="">Assign later</option>
            {board.responders.map((responder) => <option key={responder.id} value={responder.id}>{responder.full_name}</option>)}
          </select>
        </div>
      </div>
      <div className="field">
        <label htmlFor="task-safety-note">Safety note (optional)</label>
        <textarea
          id="task-safety-note"
          className="input"
          rows="2"
          maxLength="500"
          value={form.safetyNote}
          onChange={(event) => setForm({ ...form, safetyNote: event.target.value })}
        />
        <p className="help">Record site hazards only. Do not include medical or personal details.</p>
      </div>
      <div className="row gap-8">
        <button className="btn btn--primary btn--sm" disabled={creating}>{creating ? 'Creating…' : 'Create task'}</button>
        <button type="button" className="btn btn--ghost btn--sm" onClick={() => setShowCreate(false)}>Cancel</button>
      </div>
    </form>
  )
}
