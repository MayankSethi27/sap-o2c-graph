import { useRef, useCallback, useState, useImperativeHandle, forwardRef, useEffect } from "react";
import ForceGraph2D from "react-force-graph-2d";

const GraphView = forwardRef(function GraphView({ graphData, onNodeClick, onZoomChange }, ref) {
  const graphRef = useRef();
  const containerRef = useRef();
  const [hoveredNode, setHoveredNode] = useState(null);

  useImperativeHandle(ref, () => ({
    zoomToFit: () => {
      graphRef.current?.zoomToFit(500, 40);
    },
    zoomIn: () => {
      const current = graphRef.current?.zoom() || 1;
      graphRef.current?.zoom(current * 1.4, 300);
    },
    zoomOut: () => {
      const current = graphRef.current?.zoom() || 1;
      graphRef.current?.zoom(current / 1.4, 300);
    },
    getZoom: () => graphRef.current?.zoom() || 1,
  }));

  const handleNodeClick = useCallback(
    (node) => {
      if (graphRef.current && containerRef.current) {
        graphRef.current.centerAt(node.x, node.y, 500);
        graphRef.current.zoom(3, 500);

        setTimeout(() => {
          const coords = graphRef.current.graph2ScreenCoords(node.x, node.y);
          const rect = containerRef.current.getBoundingClientRect();
          onNodeClick?.({
            ...node,
            screenX: coords.x + rect.left,
            screenY: coords.y + rect.top,
            containerRect: rect,
          });
        }, 550);
      }
    },
    [onNodeClick]
  );

  const handleZoom = useCallback(
    (transform) => {
      onZoomChange?.(Math.round(transform.k * 100));
    },
    [onZoomChange]
  );

  const paintNode = useCallback((node, ctx, globalScale) => {
    const isHovered = hoveredNode === node.id;
    const radius = isHovered ? 10 : 7;

    if (isHovered) {
      ctx.beginPath();
      ctx.arc(node.x, node.y, radius + 3, 0, 2 * Math.PI);
      ctx.fillStyle = "rgba(26, 35, 126, 0.15)";
      ctx.fill();
    }

    ctx.beginPath();
    ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI);
    ctx.fillStyle = node.color || "#999";
    ctx.fill();
    ctx.strokeStyle = "rgba(255,255,255,0.8)";
    ctx.lineWidth = 1.5;
    ctx.stroke();

    if (isHovered) {
      const fontSize = Math.max(11 / globalScale, 3);
      ctx.font = `600 ${fontSize}px Sans-Serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.fillStyle = "#222";
      ctx.fillText(node.label, node.x, node.y + radius + 2);
    }
  }, [hoveredNode]);

  if (!graphData.nodes.length) {
    return <div className="graph-empty">Loading graph...</div>;
  }

  return (
    <div ref={containerRef} style={{ width: "100%", height: "100%" }}>
      <ForceGraph2D
        ref={graphRef}
        graphData={graphData}
        nodeCanvasObject={paintNode}
        nodePointerAreaPaint={(node, color, ctx) => {
          ctx.beginPath();
          ctx.arc(node.x, node.y, 10, 0, 2 * Math.PI);
          ctx.fillStyle = color;
          ctx.fill();
        }}
        onNodeHover={(node) => setHoveredNode(node ? node.id : null)}
        linkColor={() => "rgba(150,150,150,0.2)"}
        linkWidth={0.5}
        linkDirectionalArrowLength={3}
        linkDirectionalArrowRelPos={1}
        linkDirectionalArrowColor={() => "rgba(150,150,150,0.4)"}
        onNodeClick={handleNodeClick}
        onZoom={handleZoom}
        cooldownTicks={100}
        d3AlphaDecay={0.03}
        d3VelocityDecay={0.4}
      />
    </div>
  );
});

export default GraphView;
