import type { CaseReport as CaseReportData } from "../api/loadCaseReport";

export default function CaseReport({ report }: { report: CaseReportData }) {
  return (
    <section className="case-report" aria-label="Case result">
      <p className="case-cohort">
        Original {report.kept} records · {report.dropped} dropped · benchmark deaths in top 25
      </p>
      <div className="case-metrics">
        <div>
          <span>Oldest first</span>
          <b>{report.oldestDeaths}</b>
        </div>
        <div>
          <span>Points · Weight 2</span>
          <b>{report.weight2Deaths}</b>
        </div>
        <div>
          <span>Points · Weight 3</span>
          <b>{report.weight3Deaths}</b>
        </div>
        <div>
          <span>2 vs 3 overlap</span>
          <b>
            {report.overlap}/25
          </b>
        </div>
      </div>
      <p className="case-cohort">Fixed points benchmark. ML + points lists use a separate ordering.</p>
    </section>
  );
}
