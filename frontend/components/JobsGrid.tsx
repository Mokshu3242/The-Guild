"use client";

import { useMemo } from "react";
import { useRouter } from "next/navigation";
import { AgGridReact } from "ag-grid-react";
import {
  AllCommunityModule, ModuleRegistry, themeQuartz,
  type ColDef, type ICellRendererParams,
} from "ag-grid-community";
import { StatusPill } from "./ui";
import type { Me } from "@/lib/useMe";

ModuleRegistry.registerModules([AllCommunityModule]);

const theme = themeQuartz.withParams({
  fontFamily: "inherit",
  foregroundColor: "#17202a",
  accentColor: "#1e6b52",
  borderColor: "#d9dfdc",
  headerBackgroundColor: "#f4f6f5",
  headerFontWeight: 600,
  rowHoverColor: "#e3f0ea",
  wrapperBorderRadius: 8,
});

export interface Job {
  id: string;
  client_name: string;
  client_email: string;
  description: string;
  status: string;
  referrer_id: string;
  worker_id: string | null;
  match_reason: string;
  created_at: string;
}

export function JobsGrid({ jobs, members }: { jobs: Job[]; members: Me[] }) {
  const router = useRouter();
  const nameOf = (id: string | null) => members.find((m) => m.id === id)?.name ?? "Not assigned";

  const columnDefs = useMemo<ColDef<Job>[]>(() => [
    { field: "client_name", headerName: "Client", minWidth: 140 },
    { field: "description", headerName: "What they need", flex: 2, minWidth: 240, tooltipField: "description" },
    { headerName: "Posted by", valueGetter: (p) => nameOf(p.data?.referrer_id ?? null), minWidth: 110 },
    { headerName: "Worker", valueGetter: (p) => nameOf(p.data?.worker_id ?? null), minWidth: 120 },
    {
      field: "status", headerName: "Status", minWidth: 120,
      cellRenderer: (p: ICellRendererParams<Job, string>) => <StatusPill status={p.value ?? "open"} />,
    },
    {
      field: "created_at", headerName: "Posted", minWidth: 120, sort: "desc",
      valueFormatter: (p) => (p.value ? new Date(p.value).toLocaleDateString() : ""),
    },
  ], [members]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="w-full">
      <AgGridReact<Job>
        theme={theme}
        rowData={jobs}
        columnDefs={columnDefs}
        defaultColDef={{ flex: 1, sortable: true, filter: true, resizable: true }}
        domLayout="autoHeight"
        pagination
        paginationPageSize={10}
        paginationPageSizeSelector={false}
        rowStyle={{ cursor: "pointer" }}
        onRowClicked={(e) => e.data && router.push(`/jobs/view?id=${e.data.id}`)}
        overlayNoRowsTemplate="No jobs yet. Post one when a client asks for something you can't take."
      />
    </div>
  );
}