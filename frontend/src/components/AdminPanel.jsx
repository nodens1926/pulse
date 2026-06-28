import React, { useState } from "react";
import { Link } from "react-router-dom";
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
	    await addSite(siteUrl.trim());
	    setMessage("Сайт успешно добавлен");
	    setIsSuccess(true);
	    setSiteUrl("");
	} catch (err) {
	    const serverMsg = err.response?.data?.detail;
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
        <div className="min-h-screen bg-[rgb(249,249,248)]" style={{ fontFamily: '"DM Sans", sans-serif' }}>
            <header className="fixed left-0 top-0 right-0 backdrop-blur-md bg-[rgba(249,249,248,0.8)]/80 border-b border-[rgba(232,228,222,0.6)]/60 z-50">
                <div className="mx-auto w-full max-w-[1440px] px-8">
                    <div className="flex items-center justify-center h-14">
                        <Link to="/" className="flex items-center gap-2">
                            <div
                                className="flex items-center justify-center w-7 h-7 rounded-[10px]"
                                style={{
                                    backgroundImage: 'linear-gradient(135deg, rgb(30, 58, 95), rgb(45, 212, 168) 30%, rgb(168, 196, 157) 50%, rgb(232, 184, 74), rgb(255, 107, 53))'
                                }}
                            >
                                <svg className="w-4 h-4 text-white" viewBox="0 0 24 24" fill="currentColor">
                                    <circle cx="12" cy="12" r="8" />
                                </svg>
                            </div>
                            <span
                                className="block font-semibold text-[rgb(19,19,19)] text-lg tracking-[-0.45px]"
                                style={{ fontFamily: '"Space Grotesk", sans-serif' }}
                            >
                                Pulse
                            </span>
                        </Link>
                    </div>
                </div>
            </header>

            <main className="pt-24 px-8">
                <div className="mx-auto max-w-xl">
                    <h1
                        className="font-semibold text-[rgb(19,19,19)] text-3xl mb-8"
                        style={{ fontFamily: '"Space Grotesk", sans-serif' }}
                    >
                        Админ-панель
                    </h1>

                    <div className="flex flex-col sm:flex-row gap-3">
                        <input
                            className="flex-1 bg-white border border-[rgb(232,228,222)] shadow-sm rounded-xl py-3 px-4 outline-none text-[rgb(44,44,44)]"
                            type="text"
                            placeholder="https://example.com"
                            value={siteUrl}
                            onChange={(e) => setSiteUrl(e.target.value)}
                            onKeyDown={handleKeyDown}
                        />
                        <button
                            className="font-semibold bg-[rgb(45,212,168)] text-white py-3 px-6 rounded-xl hover:opacity-90 disabled:opacity-50 whitespace-nowrap"
                            onClick={handleAddSite}
                            disabled={loading}
                        >
                            {loading ? "Добавление..." : "Добавить сайт"}
                        </button>
                    </div>

                    {message && (
                        <div className={`mt-4 p-4 rounded-xl border ${
                            isSuccess
                                ? "bg-[#e8f5e9] border-[rgb(45,212,168)] text-[#2e7d32]"
                                : "bg-[#ffebee] border-[rgb(255,107,53)] text-[rgb(255,107,53)]"
                        }`}>
                            {message}
                        </div>
                    )}
                </div>
            </main>
        </div>
    );
}

export default AdminPanel;
