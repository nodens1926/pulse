import React, { useState } from "react";
import { search, addSite, getStatus } from "./api";

function App() {
    const [query, setQuery] = useState("");
    const [results, setResults] = useState([]);
    const [siteUrl, setSiteUrl] = useState("");
    const [statusMsg, setStatusMsg] = useState("");

    const handleSearch = async () => {
        try {
            const res = await search(query);
            setResults(res.data.results || []);
            setStatusMsg("");
        } catch (err) {
            setStatusMsg("Ошибка поиска");
        }
    };

    const handleAddSite = async () => {
        try {
            const res = await addSite(siteUrl);
            setStatusMsg(`Сайт добавлен: ${res.data.message || "ok"}`);
            setSiteUrl("");
        } catch (err) {
            setStatusMsg("Ошибка добавления сайта");
        }
    };

    const handleCheckStatus = async () => {
        try {
            const res = await getStatus(1);
            setStatusMsg(`Статус: ${res.data.status || "unknown"}`);
        } catch (err) {
            setStatusMsg("Ошибка проверки статуса");
        }
    };

    return (
        <div style={{ textAlign: "center", marginTop: "40px", fontFamily: "Arial" }}>
            <h1>🔍 Pulse</h1>
            <p>Поисковая система — заглушка</p>

            <div style={{ marginTop: "20px" }}>
                <input
                    type="text"
                    placeholder="Введите запрос..."
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    style={{ padding: "8px", width: "300px" }}
                />
                <button onClick={handleSearch} style={{ marginLeft: "10px", padding: "8px 16px" }}>
                    Найти
                </button>
            </div>

            <div style={{ marginTop: "20px" }}>
                <input
                    type="text"
                    placeholder="https://example.com"
                    value={siteUrl}
                    onChange={(e) => setSiteUrl(e.target.value)}
                    style={{ padding: "8px", width: "300px" }}
                />
                <button onClick={handleAddSite} style={{ marginLeft: "10px", padding: "8px 16px" }}>
                    ➕ Добавить сайт
                </button>
            </div>

            <div style={{ marginTop: "10px" }}>
                <button onClick={handleCheckStatus} style={{ padding: "8px 16px" }}>
                    📊 Проверить статус (ID=1)
                </button>
            </div>

            {statusMsg && (
                <div style={{ marginTop: "20px", color: "#555" }}>
                    <strong>{statusMsg}</strong>
                </div>
            )}

            {results.length > 0 && (
                <div style={{ marginTop: "30px", textAlign: "left", maxWidth: "600px", margin: "30px auto" }}>
                    <h3>Результаты:</h3>
                    {results.map((item, idx) => (
                        <div key={idx} style={{ border: "1px solid #ddd", padding: "10px", marginBottom: "10px" }}>
                            <a href={item.url} target="_blank" rel="noreferrer">{item.title || item.url}</a>
                        </div>
                    ))}
                </div>
            )}

            <div style={{ marginTop: "40px", fontSize: "12px", color: "#999" }}>
                Pulse — заглушка для разработки
            </div>
        </div>
    );
}

export default App;
