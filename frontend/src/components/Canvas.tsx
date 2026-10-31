import { useCallback, useEffect, useMemo, type DragEvent } from "react";
import { Background, BackgroundVariant, Controls, MiniMap, ReactFlow, useReactFlow, type Edge, type OnSelectionChangeParams } from "@xyflow/react";
import { useFlow } from "../store";
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
  const { screenToFlowPosition, fitView } = useReactFlow();

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

  const onDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault();
      const type = e.dataTransfer.getData("application/snek-tool");
      if (!type) return;
      const pos = screenToFlowPosition({ x: e.clientX - 28, y: e.clientY - 28 });
      useFlow.setState((s) => ({ selectedId: null, nodes: s.nodes.map((n) => ({ ...n, selected: false })) }));
      addNode(type, pos);
    },
    [addNode, screenToFlowPosition],
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
        deleteKeyCode={["Backspace", "Delete"]}
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
      {nodes.length === 0 && (
        <div className="empty-hint">
          <h2>Start a workflow</h2>
          <p>Drag Input Data from the left onto the canvas, or click a tool to add it.</p>
          <p>Or open a sample from File ▸ Open recent.</p>
        </div>
      )}
    </div>
  );
}
