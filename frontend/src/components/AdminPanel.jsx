import React, { useState } from "react";
import { addSite } from "../api";

function AdminPanel() {
    const [siteUrl, setSiteUrl] = useState("");
    const [message, setMessage] = useState("");
    const [isSuccess, setIsSuccess] = useState(false);
    const [loading, setLoading] = useState(false);

    const handleAddSite = async () => {
        if (!siteUrl.trim()) {
            setMessage("Введите URL сайта");
            setIsSuccess(false);
            return;
        }

        setLoading(true);
        setMessage("");

        try {
            const response = await addSite(siteUrl.trim());
            setMessage(response.data.message || "Сайт успешно добавлен");
            setIsSuccess(true);
            setSiteUrl("");
        } catch (err) {
            const serverMsg = err.response?.data?.message;
            setMessage(serverMsg || "Ошибка при добавлении сайта");
            setIsSuccess(false);
        } finally {
            setLoading(false);
        }
    };

    const handleKeyDown = (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            handleAddSite();
        }
    };

    return (
        <div className="admin-page">
            <h1>Админ-панель Pulse</h1>

            <div className="admin-form">
                <input
                    className="search-input"
                    type="text"
                    placeholder="https://example.com"
                    value={siteUrl}
                    onChange={(e) => setSiteUrl(e.target.value)}
                    onKeyDown={handleKeyDown}
                />
                <button
                    className="admin-button"
                    onClick={handleAddSite}
                    disabled={loading}
                >
                    {loading ? "Добавление..." : "Кнопка добавить сайт"}
                </button>
            </div>

            {message && (
                <div className={`message ${isSuccess ? "message-success" : "message-error"}`}>
                    {message}
                </div>
            )}
        </div>
    );
}

export default AdminPanel;
