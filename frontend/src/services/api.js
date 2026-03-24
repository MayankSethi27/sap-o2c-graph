import axios from "axios";

const api = axios.create({ baseURL: "/api" });

export async function fetchEntityTypes() {
  const { data } = await api.get("/graph/entity-types");
  return data;
}

export async function fetchEntities(entityType, limit = 50, search = "") {
  const { data } = await api.get("/graph/entities", {
    params: { entity_type: entityType, limit, search },
  });
  return data;
}

export async function traverseGraph(entityType, entityId, depth = 1) {
  const { data } = await api.get("/graph/traverse", {
    params: { entity_type: entityType, entity_id: entityId, depth },
  });
  return data;
}

export async function fetchFullGraph() {
  const { data } = await api.get("/graph/full");
  return data;
}

export async function fetchStats() {
  const { data } = await api.get("/graph/stats");
  return data;
}

export async function sendChat(message) {
  const { data } = await api.post("/chat", { message });
  return data;
}
