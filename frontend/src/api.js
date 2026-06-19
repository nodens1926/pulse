import axios from "axios";

const API = axios.create({
    baseURL: "/api",
    headers: { "Content-Type": "application/json" },
});

export const search = (query) => API.get(`/search?q=${query}`);
export const addSite = (url) => API.post("/sites", { url });
export const getStatus = (id) => API.get(`/status?site_id=${id}`);
