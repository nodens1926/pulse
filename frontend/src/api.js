import axios from "axios";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api";

export const SEARCH_ENDPOINT = "/search";
export const SITES_ENDPOINT = "/sites";

const API = axios.create({
    baseURL: API_BASE_URL,
    headers: { "Content-Type": "application/json" },
});

export const search = (query) =>
    API.get(`${SEARCH_ENDPOINT}?q=${encodeURIComponent(query)}`);

export const addSite = (url) =>
    API.post(SITES_ENDPOINT, { url });

export const getStatus = (id) => API.get(`/status/${id}`);
