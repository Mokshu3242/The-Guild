"use client";

/**
 * 14B "Who's free" on Bryntum Scheduler (sponsor tool, trial build).
 * Loaded only in the browser (next/dynamic, ssr: false) because Bryntum needs `window`.
 * Read-only: bookings are estimates from GET /capacity, nothing here edits them.
 */
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { BryntumScheduler } from "@bryntum/scheduler-react";
import { StringHelper, type EventModel, type Model, type Scheduler, type Widget } from "@bryntum/scheduler";
import "@bryntum/scheduler/scheduler.css";
import "@bryntum/scheduler/svalbard-light.css";
import "@bryntum/scheduler/fontawesome/css/fontawesome.css";
import "@bryntum/scheduler/fontawesome/css/solid.css";
import { usd } from "@/lib/format";
import { addDays, freeText, shortDate, type Capacity } from "@/lib/capacity";

const ROW = 48;

// Bryntum reads "YYYY-MM-DD" as local midnight, so the bars line up with the day columns.
const local = (iso: string) => {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
};

export default function CapacityScheduler({ data }: { data: Capacity }) {
  const router = useRouter();
  // Wide screens: fit both weeks in view. Phones: keep readable day columns and scroll sideways.
  // This component only runs in the browser (ssr: false), so window is always there.
  const [wide] = useState(() => window.innerWidth >= 768);

  const { resources, events, ranges } = useMemo(() => {
    const resources = data.members.map((m) => ({
      id: m.id,
      name: m.name,
      status: freeText(m, data.today),
    }));
    const events = data.members.flatMap((m) =>
      m.bookings.map((b, i) => ({
        id: `${m.id}-${i}`,
        resourceId: m.id,
        name: b.client,
        startDate: local(b.start),
        endDate: local(addDays(b.end, 1)), // Bryntum end dates are exclusive
        jobId: b.job_id,
        workCents: b.work_cents,
        workDays: b.days,
        endLabel: b.end,
      })),
    );
    const ranges = data.members.flatMap((m) => {
      if (m.state === "off")
        return [{ id: `off-${m.id}`, resourceId: m.id, startDate: local(data.today), endDate: local(addDays(data.start, data.days)), name: "Not taking work" }];
      if (m.away_until && m.away_until > data.today)
        return [{ id: `away-${m.id}`, resourceId: m.id, startDate: local(data.today), endDate: local(m.away_until), name: "Away" }];
      return [];
    });
    return { resources, events, ranges };
  }, [data]);

  return (
    <div className="guild-scheduler overflow-hidden rounded-lg border border-line" style={{ height: 72 + ROW * Math.max(1, resources.length) }}>
      {/* Keep the red "now" line but hide its clock label (it covers today's date). Weekends in our muted
          colors instead of Bryntum's pink. Short bars end with "…" instead of cutting a word; the tooltip has the full name. */}
      <style>{`
        .guild-scheduler .b-grid-header-container .b-sch-current-time{display:none}
        .guild-scheduler .b-time-ranges-header-canvas .b-sch-non-working-time{background:transparent}
        .guild-scheduler .b-sch-day-header-cell-6,.guild-scheduler .b-sch-day-header-cell-0{background:#f3f5f2;color:#5a6762}
        .guild-scheduler .b-sch-event-content{font-size:14px;margin-inline:2px;min-width:0;overflow:hidden}
        .guild-scheduler .b-sch-event-content>*{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
        .guild-scheduler .b-sch-event{padding-inline:8px}
      `}</style>
      <BryntumScheduler
        readOnly
        startDate={local(data.start)}
        endDate={local(addDays(data.start, data.days))}
        viewPreset="dayAndWeek"
        weekStartDay={1}
        rowHeight={ROW}
        barMargin={9}
        eventStyle="rounded"
        eventColor="#a87a1f"
        eventRenderer={({ eventRecord }: { eventRecord: EventModel }) =>
          `<span>${StringHelper.encodeHtml(eventRecord.name)}</span>`
        }
        forceFit={wide}
        onPaint={({ source, firstPaint }: { source: Widget; firstPaint: boolean }) => {
          if (firstPaint && !wide) (source as Scheduler).scrollToDate(local(data.today), { block: "start", animate: false });
        }}
        columns={[
          {
            text: "Member",
            field: "name",
            width: 128,
            sortable: false,
            htmlEncode: false,
            renderer: ({ record }: { record: Model }) =>
              `<div style="line-height:1.25"><div style="font-weight:600">${StringHelper.encodeHtml(
                String(record.getData("name")),
              )}</div><div style="font-size:.8em;opacity:.7">${StringHelper.encodeHtml(String(record.getData("status")))}</div></div>`,
          },
        ]}
        resources={resources}
        events={events}
        resourceTimeRanges={ranges}
        resourceTimeRangesFeature
        scheduleTooltipFeature={false}
        nonWorkingTimeFeature
        timeRangesFeature={{ showCurrentTimeLine: true }}
        eventTooltipFeature={{
          template: ({ eventRecord }: { eventRecord: EventModel }) => {
            const cents = Number(eventRecord.getData("workCents")) || 0;
            const days = Number(eventRecord.getData("workDays")) || 0;
            const end = String(eventRecord.getData("endLabel") ?? "");
            return `<b>${StringHelper.encodeHtml(eventRecord.name)}</b><br>${StringHelper.encodeHtml(
              `${usd(cents)} of work left, about ${days} working day${days === 1 ? "" : "s"}, until ${shortDate(end)}`,
            )}`;
          },
        }}
        onEventClick={({ eventRecord }: { eventRecord: EventModel }) => {
          const id = eventRecord.getData("jobId");
          if (id) router.push(`/jobs/view/?id=${id}`);
        }}
      />
    </div>
  );
}
