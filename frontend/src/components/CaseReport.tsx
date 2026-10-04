import type { CaseReport as CaseReportData } from "../api/loadCaseReport";

export default function CaseReport({ report }: { report: CaseReportData }) {
  return (
    <section className="case-report" aria-label="Case result">
      <div className="panel-heading"><div><p className="eyebrow">Original public cohort</p><h3>Historical benchmark</h3></div></div>
      <p className="case-cohort">
        {report.kept} records · {report.dropped} dropped · later deaths in top 25
      </p>
      <div className="case-metrics">
        <div>
          <span>Oldest first</span>
          <b>{report.oldestDeaths}</b>
        </div>
        <div>
          <span>Weight 2</span>
          <b>{report.weight2Deaths}</b>
        </div>
        <div>
          <span>Weight 3</span>
          <b>{report.weight3Deaths}</b>
        </div>
        <div>
          <span>2 vs 3 overlap</span>
          <b>
            {report.overlap}/25
          </b>
        </div>
      </div>
      <p className="case-cohort">Same lists as the call-list buttons. Model is its own tab.</p>
    </section>
  );
}
