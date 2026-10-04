import { useRef, type KeyboardEvent } from "react";
import InterfaceIcon, { type IconName } from "./InterfaceIcon";

export type WorkspaceTab = "dashboard" | "guide" | "about";
const tabs: { id: WorkspaceTab; label: string; icon: IconName }[] = [
  { id: "dashboard", label: "Dashboard", icon: "dashboard" },
  { id: "guide", label: "Field guide", icon: "book" },
  { id: "about", label: "About the program", icon: "info" },
];

/** Manual activation keeps arrow-key exploration from changing the active workspace. */
export default function WorkspaceTabs({ active, onChange }: { active: WorkspaceTab; onChange: (tab: WorkspaceTab) => void }) {
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  function moveFocus(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next: number;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    else if (event.key === "ArrowLeft") next = (index + tabs.length - 1) % tabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    else return;
    event.preventDefault();
    buttons.current[next]?.focus();
  }
  return <div className="workspace-tabs" role="tablist" aria-label="Workspace navigation">
    {tabs.map((tab, index) => <button key={tab.id} id={`tab-${tab.id}`} role="tab"
      ref={(element) => { buttons.current[index] = element; }}
      aria-selected={active === tab.id} aria-controls={`panel-${tab.id}`}
      tabIndex={active === tab.id ? 0 : -1}
      onClick={() => onChange(tab.id)} onKeyDown={(event) => moveFocus(event, index)}>
      <InterfaceIcon name={tab.icon} /><span>{tab.label}</span>
    </button>)}
  </div>;
}
