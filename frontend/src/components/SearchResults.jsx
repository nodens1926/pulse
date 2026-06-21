import React, { useState, useEffect, useCallback } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { search } from "../api";

function SearchResults() {
    const [searchParams, setSearchParams] = useSearchParams();
    const queryFromUrl = searchParams.get("q") || "";

    const [query, setQuery] = useState(queryFromUrl);
    const [results, setResults] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");

    const fetchResults = useCallback(async (searchQuery) => {
        if (!searchQuery.trim()) return;

        setLoading(true);
        setError("");
        setResults([]);

        try {
            const response = await search(searchQuery);
            const items = response.data.results || [];

            if (items.length === 0) {
                setError("Ничего не найдено");
            } else {
                setResults(items);
            }
        } catch (err) {
            setError("Ошибка сети. Проверьте подключение к серверу.");
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        setQuery(queryFromUrl);
        if (queryFromUrl) {
            fetchResults(queryFromUrl);
        }
    }, [queryFromUrl, fetchResults]);

    const handleKeyDown = (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            const trimmed = query.trim();
            if (trimmed) {
                setSearchParams({ q: trimmed });
            }
        }
    };

    return (
        <div>
            <header className="search-header">
                <Link to="/" className="logo">
                    Pulse
                </Link>
                <input
                    className="search-input"
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={handleKeyDown}
                />
            </header>

            <div className="results-container">
                {loading && <p className="loading">Загрузка...</p>}

                {error && !loading && (
                    <div className="message message-error">{error}</div>
                )}

                {!loading && !error && results.map((item, index) => (
                    <div className="result-item" key={index}>
                        <a href={item.url} target="_blank" rel="noopener noreferrer">
                            {item.title || item.url}
                        </a>
                        {item.url && <div className="result-url">{item.url}</div>}
                        {item.snippet && <div className="result-snippet">{item.snippet}</div>}
                    </div>
                ))}
            </div>
        </div>
    );
}

export default SearchResults;
