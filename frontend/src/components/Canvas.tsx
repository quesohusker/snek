import { useCallback, useEffect, useMemo, useState, type DragEvent, type MouseEvent as ReactMouseEvent } from "react";
import { Background, BackgroundVariant, Controls, MiniMap, ReactFlow, SelectionMode, useReactFlow, type Edge, type Node, type OnSelectionChangeParams } from "@xyflow/react";
import { useFlow, type ToolNode } from "../store";
import { api } from "../api";
import { copyTools, cutTools, pasteTools } from "../editing";
import { openDroppedWorkflow, runWorkflow } from "../commands";
import { keyLabel } from "../paths";
import ContextMenu, { type ContextMenuState } from "./ContextMenu";
import type { MenuItem } from "./Menubar";
import ToolNodeView from "./ToolNodeView";
import { CATEGORY_COLORS } from "../icons";

const nodeTypes = { tool: ToolNodeView };

export default function Canvas() {
  const nodes = useFlow((s) => s.nodes);
  const edges = useFlow((s) => s.edges);
  const results = useFlow((s) => s.results);
  const stale = useFlow((s) => s.stale);
  const tools = useFlow((s) => s.tools);
  const onNodesChange = useFlow((s) => s.onNodesChange);
  const onEdgesChange = useFlow((s) => s.onEdgesChange);
  const onConnect = useFlow((s) => s.onConnect);
  const canConnect = useFlow((s) => s.canConnect);
  const addNode = useFlow((s) => s.addNode);
  const select = useFlow((s) => s.select);
  const loaded = useFlow((s) => s.loaded);
  const { screenToFlowPosition, fitView, zoomTo } = useReactFlow();
  const [menu, setMenu] = useState<ContextMenuState>(null);
  const closeMenu = useCallback(() => setMenu(null), []);

  const toolItems = useCallback((single: ToolNode | null): MenuItem[] => {
    const s = useFlow.getState();
    return [
      { label: "Cut", shortcut: keyLabel("mod+X"), onSelect: cutTools },
      { label: "Copy", shortcut: keyLabel("mod+C"), onSelect: copyTools },
      { label: "Paste", shortcut: keyLabel("mod+V"), onSelect: () => pasteTools() },
      { label: "Duplicate", shortcut: keyLabel("mod+D"), onSelect: s.duplicateSelected },
      { label: "Delete", shortcut: "⌫", onSelect: () => useFlow.getState().deleteSelected() },
      { type: "separator" },
      { label: "Rename…", onSelect: single ? () => useFlow.getState().requestRename(single.id) : undefined, disabled: !single },
      { label: "Run workflow", shortcut: keyLabel("mod+↵"), onSelect: () => runWorkflow() },
    ];
  }, []);

  const onNodeContextMenu = useCallback(
    (e: ReactMouseEvent, node: Node) => {
      e.preventDefault();
      const s = useFlow.getState();
      if (!node.selected) s.select(node.id);
      const many = useFlow.getState().nodes.filter((n) => n.selected).length > 1;
      setMenu({ x: e.clientX, y: e.clientY, items: toolItems(many ? null : (node as ToolNode)) });
    },
    [toolItems],
  );

  const onSelectionContextMenu = useCallback(
    (e: ReactMouseEvent) => {
      e.preventDefault();
      setMenu({ x: e.clientX, y: e.clientY, items: toolItems(null) });
    },
    [toolItems],
  );

  const onPaneContextMenu = useCallback(
    (e: ReactMouseEvent | MouseEvent) => {
      e.preventDefault();
      const at = screenToFlowPosition({ x: e.clientX, y: e.clientY });
      const s = useFlow.getState();
      setMenu({
        x: e.clientX,
        y: e.clientY,
        items: [
          { label: "Paste here", shortcut: keyLabel("mod+V"), onSelect: () => pasteTools(at) },
          { label: "Select all", shortcut: keyLabel("mod+A"), onSelect: s.selectAll, disabled: !s.nodes.length },
          { type: "separator" },
          { label: "Undo", shortcut: keyLabel("mod+Z"), onSelect: s.undo, disabled: !s.past.length },
          { label: "Redo", shortcut: keyLabel("mod+shift+Z"), onSelect: s.redo, disabled: !s.future.length },
          { type: "separator" },
          { label: "Fit to screen", shortcut: keyLabel("shift+1"), onSelect: () => fitView({ padding: 0.2, maxZoom: 1.1, duration: 200 }) },
          { label: "Actual size", shortcut: keyLabel("mod+0"), onSelect: () => zoomTo(1, { duration: 150 }) },
        ],
      });
    },
    [screenToFlowPosition, fitView, zoomTo],
  );

  const onEdgeContextMenu = useCallback((e: ReactMouseEvent, edge: Edge) => {
    e.preventDefault();
    setMenu({ x: e.clientX, y: e.clientY, items: [{ label: "Delete connection", onSelect: () => useFlow.getState().onEdgesChange([{ type: "remove", id: edge.id }]) }] });
  }, []);

  useEffect(() => {
    if (!loaded) return;
    const t = setTimeout(() => fitView({ padding: 0.2, maxZoom: 1.1 }), 50);
    return () => clearTimeout(t);
  }, [loaded, fitView]);

  const labeled = useMemo<Edge[]>(
    () =>
      edges.map((e) => {
        const rows = results[e.source]?.outputs?.[e.sourceHandle ?? "out"]?.rows;
        return rows === undefined
          ? { ...e, label: undefined }
          : { ...e, label: rows.toLocaleString(), className: stale ? "stale" : "", labelBgPadding: [4, 2] as [number, number], labelBgBorderRadius: 4 };
      }),
    [edges, results, stale],
  );

  const onDragOver = useCallback((e: DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  }, []);

  const dropFiles = useCallback(
    async (files: File[], x: number, y: number) => {
      for (const [i, file] of files.entries()) {
        if (/\.(snek|flow\.json)$/i.test(file.name)) {
          await openDroppedWorkflow(file);
          return;
        }
        try {
          const { path } = await api.upload(file);
          const s = useFlow.getState();
          s.selectNone();
          const id = s.addNode("input", screenToFlowPosition({ x: x - 28, y: y - 28 + i * 110 }));
          useFlow.getState().updateConfig(id, { path });
          useFlow.setState((st) => ({ past: st.past.slice(0, -1) }));
        } catch (err) {
          alert(`Could not add ${file.name}: ${(err as Error).message}`);
        }
      }
    },
    [screenToFlowPosition],
  );

  const onDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault();
      if (e.dataTransfer.files?.length) {
        dropFiles(Array.from(e.dataTransfer.files), e.clientX, e.clientY);
        return;
      }
      const type = e.dataTransfer.getData("application/snek-tool");
      if (!type) return;
      const pos = screenToFlowPosition({ x: e.clientX - 28, y: e.clientY - 28 });
      useFlow.setState((s) => ({ selectedId: null, nodes: s.nodes.map((n) => ({ ...n, selected: false })) }));
      addNode(type, pos);
    },
    [addNode, screenToFlowPosition, dropFiles],
  );

  const onSelectionChange = useCallback(
    ({ nodes: picked }: OnSelectionChangeParams) => {
      if (picked.length === 1) select(picked[0].id);
      else if (picked.length === 0) select(null);
    },
    [select],
  );

  return (
    <div className="canvas" onDragOver={onDragOver} onDrop={onDrop}>
      <ReactFlow
        nodes={nodes}
        edges={labeled}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        isValidConnection={canConnect}
        onSelectionChange={onSelectionChange}
        onNodeContextMenu={onNodeContextMenu}
        onSelectionContextMenu={onSelectionContextMenu}
        onPaneContextMenu={onPaneContextMenu}
        onEdgeContextMenu={onEdgeContextMenu}
        onMoveStart={closeMenu}
        deleteKeyCode={null}
        selectionOnDrag
        selectionMode={SelectionMode.Partial}
        panOnDrag={[1]}
        panOnScroll
        zoomOnPinch
        zoomActivationKeyCode={["Meta", "Control"]}
        multiSelectionKeyCode={["Meta", "Control", "Shift"]}
        colorMode="system"
        fitView
        fitViewOptions={{ maxZoom: 1.1, padding: 0.2 }}
        minZoom={0.2}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={18} size={1} />
        <Controls showInteractive={false} />
        <MiniMap pannable zoomable style={{ width: 150, height: 96 }} nodeColor={(n) => CATEGORY_COLORS[tools[(n.data as { type: string }).type]?.category] ?? "#888"} />
      </ReactFlow>
      <ContextMenu menu={menu} onClose={closeMenu} />
      {nodes.length === 0 && (
        <div className="empty-hint">
          <h2>Start a workflow</h2>
          <p>Drag Input Data from the left onto the canvas, or click a tool to add it.</p>
          <p>Or open a sample from File ▸ Open recent, or drop a data file here.</p>
        </div>
      )}
    </div>
  );
}
