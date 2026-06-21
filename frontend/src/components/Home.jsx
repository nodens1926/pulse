import React, { useState } from "react";
import { useNavigate } from "react-router-dom";

function Home() {
    const [query, setQuery] = useState("");
    const navigate = useNavigate();

    const handleKeyDown = (e) => {
        if (e.key === "Enter" && query.trim()) {
            navigate(`/search?q=${encodeURIComponent(query.trim())}`);
        }
    };

    return (
        <div className="home-page">
            <span className="logo">Pulse</span>
            <input
                className="search-input"
                type="text"
                placeholder="Поиск 🔍"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                autoFocus
            />
        </div>
    );
}

export default Home;
