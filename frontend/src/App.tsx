import { ArrowUpRight, Compass, Sparkles } from "lucide-react";

const setupSteps = [
  "React + TypeScript application scaffolded",
  "Tailwind CSS v4 connected through Vite",
  "LedgerLens typography and colour tokens added",
];

function App() {
  return (
    <main className="min-h-screen bg-[var(--color-canvas)] px-6 py-12 text-[var(--color-ink)] sm:px-10">
      <div className="mx-auto flex max-w-5xl flex-col gap-12">
        <header className="flex items-center gap-3">
          <div className="flex size-11 items-center justify-center rounded-2xl bg-[var(--color-forest)] text-white">
            <Compass size={23} strokeWidth={1.6} />
          </div>
          <div>
            <p className="font-display text-lg font-bold tracking-tight">LedgerLens</p>
            <p className="text-xs text-[var(--color-muted)]">See beyond the numbers.</p>
          </div>
        </header>

        <section className="grid gap-8 rounded-[2rem] border border-[var(--color-line)] bg-white p-8 shadow-[0_20px_70px_rgba(38,51,47,0.06)] sm:p-12 md:grid-cols-[1.3fr_0.7fr] md:items-end">
          <div>
            <div className="mb-6 inline-flex items-center gap-2 rounded-full bg-[var(--color-sage)] px-3 py-1.5 text-xs font-semibold text-[var(--color-forest)]">
              <Sparkles size={14} /> Your financial clarity starts here
            </div>
            <h1 className="max-w-xl font-display text-4xl font-semibold leading-[1.12] tracking-[-0.045em] sm:text-5xl">
              Make every business decision with <span className="text-[var(--color-forest)]">confidence.</span>
            </h1>
            <p className="mt-5 max-w-lg text-base leading-7 text-[var(--color-muted)]">
              A clearer view of your cash flow, risks and next move. We’re building your AI-powered financial workspace one thoughtful step at a time.
            </p>
          </div>
          <div className="rounded-2xl bg-[var(--color-paper)] p-5">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--color-muted)]">Build progress</p>
            <div className="mt-4 space-y-4">
              {setupSteps.map((step, index) => (
                <div className="flex items-start gap-3" key={step}>
                  <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-[var(--color-sage)] text-xs font-bold text-[var(--color-forest)]">{index + 1}</span>
                  <p className="text-sm leading-6 text-[var(--color-ink)]">{step}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <footer className="flex items-center justify-between border-t border-[var(--color-line)] pt-5 text-xs text-[var(--color-muted)]">
          <span>LedgerLens · Frontend foundation</span>
          <span className="inline-flex items-center gap-1">Explore the build <ArrowUpRight size={13} /></span>
        </footer>
      </div>
    </main>
  );
}

export default App;
