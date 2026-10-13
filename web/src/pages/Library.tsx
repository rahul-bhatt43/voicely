import { Plus } from "lucide-react";
import { Link } from "react-router-dom";
import { isActive, type Job } from "../api";
import { JobCard } from "../components/JobCard";
import { Empty, ErrorNote, PageHeader, Spinner } from "../components/ui";
import { usePolled } from "../hooks";

export default function Library() {
  // Poll quickly only while something is actually in progress.
  const { data: jobs, error, reload } = usePolled<Job[]>("/jobs", (list) => (list?.some(isActive) ? 2000 : 15000));

  const active = jobs?.filter(isActive) ?? [];
  const done = jobs?.filter((j) => !isActive(j)) ?? [];

  return (
    <>
      <PageHeader eyebrow="Library" title="Everything you've made"
        action={<Link to="/" className="btn btn-primary"><Plus className="size-4" /> New</Link>}>
        Results stay here until you delete them. You can leave this page while a job runs.
      </PageHeader>

      <ErrorNote>{error}</ErrorNote>
      {!jobs && !error && <Spinner className="size-5 text-muted" />}

      {jobs?.length === 0 && (
        <Empty title="Nothing here yet" action={<Link to="/" className="btn btn-primary">Make something</Link>}>
          Covers, voice swaps and training runs show up here as soon as you start one.
        </Empty>
      )}

      {active.length > 0 && (
        <section className="mb-10">
          <h2 className="eyebrow mb-3">In progress</h2>
          <div className="grid grid-cols-1 gap-4">{active.map((j) => <JobCard key={j.id} job={j} onChanged={reload} />)}</div>
        </section>
      )}

      {done.length > 0 && (
        <section>
          {active.length > 0 && <h2 className="eyebrow mb-3">Finished</h2>}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 items-start">{done.map((j) => <JobCard key={j.id} job={j} onChanged={reload} />)}</div>
        </section>
      )}
    </>
  );
}
