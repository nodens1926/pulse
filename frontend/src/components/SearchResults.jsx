import React, { useState, useEffect, useCallback, useRef } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { search } from "../api";

function SearchResults() {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryFromUrl = searchParams.get("q") || "";

  const [query, setQuery] = useState(queryFromUrl);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  
  // Предотвращаем дублирующиеся запросы
  const fetchingRef = useRef(false);
  const lastQueryRef = useRef("");

  const fetchResults = useCallback(async (searchQuery) => {
    if (!searchQuery.trim()) return;
    
    // Если уже идёт запрос или тот же запрос уже выполняется — пропускаем
    if (fetchingRef.current || lastQueryRef.current === searchQuery) {
      return;
    }

    fetchingRef.current = true;
    lastQueryRef.current = searchQuery;
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
      fetchingRef.current = false;
    }
  }, []);

  useEffect(() => {
    setQuery(queryFromUrl);
    // Сбрасываем ref при новом запросе
    if (queryFromUrl) {
      fetchingRef.current = false;
      fetchResults(queryFromUrl);
    }
  }, [queryFromUrl, fetchResults]);

  const handleSubmit = (e) => {
    e.preventDefault();
    const trimmed = query.trim();
    if (trimmed) {
      setSearchParams({ q: trimmed });
    }
  };

  return (
    <div className="min-h-screen bg-[rgb(249,249,248)]" style={{ fontFamily: '"DM Sans", sans-serif' }}>
      {/* Header */}
      <header className="fixed left-0 top-0 right-0 backdrop-blur-md bg-[rgba(249,249,248,0.8)]/80 border-b border-[rgba(232,228,222,0.6)]/60 z-50">
        <div className="mx-auto w-full max-w-[1440px] px-8">
          <div className="flex items-center justify-between h-14">
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

            {/* Поисковая строка в хедере страницы результатов */}
            <form onSubmit={handleSubmit} className="flex items-center bg-white border border-[rgb(232,228,222)] shadow-sm gap-3 py-2 px-4 rounded-[20px] w-full max-w-md">
              <svg className="w-5 h-5 text-[rgba(44,44,44,0.4)]/40 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <circle cx="11" cy="11" r="8" strokeWidth="2" />
                <path d="M21 21l-4.35-4.35" strokeWidth="2" strokeLinecap="round" />
              </svg>
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search sites, URLs, or content…"
                className="block grow bg-transparent outline-none text-[rgb(44,44,44)]"
              />
              <button
                type="submit"
                className="font-semibold text-center bg-[rgb(241,239,234)] text-[rgba(44,44,44,0.4)]/40 text-sm leading-5 py-2 px-5 rounded-xl transition-colors duration-200 hover:bg-[rgb(45,212,168)] hover:text-white cursor-pointer"
              >
                Search
              </button>
            </form>
          </div>
        </div>
      </header>

      {/* Основной контент */}
      <main className="pt-20">
        <div className="mx-auto max-w-[1440px] px-8 py-8">
          <div className="max-w-3xl mx-auto">
            {/* Загрузка */}
            {loading && (
              <div className="text-center py-16">
                <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-[rgb(45,212,168)]" />
                <p className="mt-4 text-[rgba(44,44,44,0.6)]">Searching...</p>
              </div>
            )}

            {/* Ошибка */}
            {!loading && error && (
              <div className="bg-white border border-[rgb(232,228,222)] shadow-sm rounded-2xl p-6 text-center">
                <p className="text-[rgb(255,107,53)] font-medium">{error}</p>
              </div>
            )}

            {/* Результаты поиска */}
            {!loading && !error && results.length > 0 && (
              <div>
                <p className="text-sm text-[rgba(44,44,44,0.5)] mb-4">
                  Found {results.length} result{results.length !== 1 ? 's' : ''}
                </p>
                <div className="space-y-4">
                  {results.map((item, index) => (
                    <div
                      key={index}
                      className="bg-white border border-[rgb(232,228,222)] shadow-sm rounded-2xl p-6 hover:shadow-md transition-shadow"
                    >
                      <a
                        href={item.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-[rgb(30,58,95)] font-semibold text-lg hover:underline"
                      >
                        {item.title || item.url}
                      </a>
                      {item.url && (
                        <div className="text-[rgb(45,212,168)] text-sm mt-1 truncate">
                          {item.url}
                        </div>
                      )}
                      {/* СНИППЕТ - первые 200 символов текста */}
                      {item.snippet && (
                        <p className="text-[rgba(44,44,44,0.6)] text-sm mt-2 line-clamp-3">
                          {item.snippet}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Ничего не найдено */}
            {!loading && !error && results.length === 0 && queryFromUrl && (
              <div className="bg-white border border-[rgb(232,228,222)] shadow-sm rounded-2xl p-12 text-center">
                <svg className="w-12 h-12 text-[rgba(44,44,44,0.2)] mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
                <p className="text-[rgba(44,44,44,0.6)] text-lg">No results found for “{queryFromUrl}”</p>
                <p className="text-[rgba(44,44,44,0.4)] mt-2">Try a different search term or check the URL</p>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

export default SearchResults;
