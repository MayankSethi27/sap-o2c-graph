import { useState, useMemo, useCallback, useRef, useEffect } from "react";
import GraphView from "./components/GraphView";
import NodeDetail from "./components/NodeDetail";
import ChatPanel from "./components/ChatPanel";
import Legend from "./components/Legend";
import useGraph from "./hooks/useGraph";

export default function App() {
  const { graphData, loading } = useGraph();
  const [selectedNode, setSelectedNode] = useState(null);
  const [zoomPercent, setZoomPercent] = useState(100);
  const [chatWidth, setChatWidth] = useState(30); // percentage
  const graphViewRef = useRef();
  const draggingRef = useRef(false);

  const handleMinimize = useCallback(() => {
    setSelectedNode(null);
    graphViewRef.current?.zoomToFit();
  }, []);

  const handleZoomIn = useCallback(() => {
    graphViewRef.current?.zoomIn();
  }, []);

  const handleZoomOut = useCallback(() => {
    graphViewRef.current?.zoomOut();
  }, []);

  // Resizable divider drag
  const handleDividerMouseDown = useCallback((e) => {
    e.preventDefault();
    draggingRef.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

  useEffect(() => {
    const handleMouseMove = (e) => {
      if (!draggingRef.current) return;
      const pct = ((window.innerWidth - e.clientX) / window.innerWidth) * 100;
      setChatWidth(Math.min(60, Math.max(15, pct)));
    };
    const handleMouseUp = () => {
      if (draggingRef.current) {
        draggingRef.current = false;
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
      }
    };
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, []);

  const connectionCount = useMemo(() => {
    if (!selectedNode) return 0;
    return graphData.links.filter((l) => {
      const src = typeof l.source === "object" ? l.source.id : l.source;
      const tgt = typeof l.target === "object" ? l.target.id : l.target;
      return src === selectedNode.id || tgt === selectedNode.id;
    }).length;
  }, [selectedNode, graphData.links]);

  const cardStyle = useMemo(() => {
    if (!selectedNode || !selectedNode.containerRect) return {};
    const { screenX, screenY, containerRect } = selectedNode;
    let left = screenX + 20;
    let top = screenY - 40;
    const cardWidth = 320;
    if (left + cardWidth > containerRect.right) {
      left = screenX - cardWidth - 20;
    }
    top = Math.max(containerRect.top + 10, top);
    top = Math.min(containerRect.bottom - 200, top);
    return { left, top };
  }, [selectedNode]);

  const handleNodeClick = useCallback((node) => {
    setSelectedNode(node);
  }, []);

  const handleCloseCard = useCallback(() => {
    setSelectedNode(null);
  }, []);

  return (
    <div className="app">
      <header>
        <h1>SAP O2C Graph Explorer</h1>
        <span className="stats">
          {graphData.nodes.length} nodes &middot; {graphData.links.length} edges
        </span>
      </header>

      <div className="main-content">
        <div className="graph-section" style={{ flex: `${100 - chatWidth} 0 0` }}>
          <div className="graph-container">
            {loading && <div className="loading-overlay">Loading graph...</div>}
            <GraphView
              ref={graphViewRef}
              graphData={graphData}
              onNodeClick={handleNodeClick}
              onZoomChange={setZoomPercent}
            />

            {/* Graph controls — top-left */}
            <div className="graph-controls">
              <button className="graph-ctrl-btn" onClick={handleMinimize} title="Fit all nodes">Minimize</button>
              <div className="zoom-controls">
                <button className="graph-ctrl-btn" onClick={handleZoomOut} title="Zoom out">&minus;</button>
                <span className="zoom-level">{zoomPercent}%</span>
                <button className="graph-ctrl-btn" onClick={handleZoomIn} title="Zoom in">+</button>
              </div>
            </div>

            <Legend />
          </div>

          {selectedNode && (
            <div className="node-card-wrapper" style={{ left: cardStyle.left, top: cardStyle.top }}>
              <NodeDetail
                node={selectedNode}
                connectionCount={connectionCount}
                onClose={handleCloseCard}
              />
            </div>
          )}
        </div>

        {/* Draggable divider */}
        <div className="resize-divider" onMouseDown={handleDividerMouseDown} />

        <aside className="chat-sidebar" style={{ flex: `${chatWidth} 0 0`, minWidth: 0 }}>
          <ChatPanel />
        </aside>
      </div>
    </div>
  );
}
