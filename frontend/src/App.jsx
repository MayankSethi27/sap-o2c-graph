import { useState, useMemo, useCallback, useRef } from "react";
import GraphView from "./components/GraphView";
import NodeDetail from "./components/NodeDetail";
import ChatPanel from "./components/ChatPanel";
import Legend from "./components/Legend";
import useGraph from "./hooks/useGraph";

export default function App() {
  const { graphData, loading } = useGraph();
  const [selectedNode, setSelectedNode] = useState(null);
  const graphViewRef = useRef();

  const handleMinimize = useCallback(() => {
    setSelectedNode(null);
    graphViewRef.current?.zoomToFit();
  }, []);

  // Count connections for the selected node
  const connectionCount = useMemo(() => {
    if (!selectedNode) return 0;
    return graphData.links.filter((l) => {
      const src = typeof l.source === "object" ? l.source.id : l.source;
      const tgt = typeof l.target === "object" ? l.target.id : l.target;
      return src === selectedNode.id || tgt === selectedNode.id;
    }).length;
  }, [selectedNode, graphData.links]);

  // Compute floating card position
  const cardStyle = useMemo(() => {
    if (!selectedNode || !selectedNode.containerRect) return {};
    const { screenX, screenY, containerRect } = selectedNode;

    // Position card to the right of the node, offset by 20px
    let left = screenX + 20;
    let top = screenY - 40;

    // If card would overflow right edge, show it to the left
    const cardWidth = 320;
    if (left + cardWidth > containerRect.right) {
      left = screenX - cardWidth - 20;
    }

    // Keep within vertical bounds
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
        <div className="graph-section">
          <div className="graph-container">
            {loading && <div className="loading-overlay">Loading graph...</div>}
            <GraphView ref={graphViewRef} graphData={graphData} onNodeClick={handleNodeClick} />
            <button className="minimize-btn" onClick={handleMinimize}>Minimize</button>
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

        <aside className="chat-sidebar">
          <ChatPanel />
        </aside>
      </div>
    </div>
  );
}
