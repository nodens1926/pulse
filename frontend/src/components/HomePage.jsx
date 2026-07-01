import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Link } from "react-router-dom";
import axios from "axios";

function HomePage() {
  const [query, setQuery] = useState("");
  const navigate = useNavigate();

  // Состояния для статистики
  const [stats, setStats] = useState({
    sites: 0,
    pages: 0,
    lastSync: "Loading...",
    queries: 0
  });
  const [loading, setLoading] = useState(true);

  // Загрузка статистики при монтировании
  useEffect(() => {
    const fetchStats = async () => {
      try {
        const response = await axios.get('/api/status');
        const sites = response.data || [];
        
        // Считаем общее количество страниц
        let totalPages = 0;
        sites.forEach(site => {
          totalPages += site.pages_indexed || 0;
        });

        // Находим последнюю синхронизацию (самый свежий сайт)
        let lastSync = "Never";
        if (sites.length > 0) {
          // Сортируем по дате добавления
          const sorted = [...sites].sort((a, b) => 
            new Date(b.date_added) - new Date(a.date_added)
          );
          if (sorted[0]?.date_added) {
            const date = new Date(sorted[0].date_added);
            const now = new Date();
            const diffMs = now - date;
            const diffMins = Math.floor(diffMs / 60000);
            const diffHours = Math.floor(diffMins / 60);
            const diffDays = Math.floor(diffHours / 24);
            
            if (diffDays > 0) {
              lastSync = `${diffDays}d ago`;
            } else if (diffHours > 0) {
              lastSync = `${diffHours}h ago`;
            } else if (diffMins > 0) {
              lastSync = `${diffMins}m ago`;
            } else {
              lastSync = "Just now";
            }
          }
        }

        setStats({
          sites: sites.length,
          pages: totalPages,
          lastSync: lastSync,
          queries: sites.length * 100 // Примерная заглушка (можно убрать или заменить)
        });
      } catch (error) {
        console.error("Ошибка загрузки статистики:", error);
        setStats({
          sites: 0,
          pages: 0,
          lastSync: "Error",
          queries: 0
        });
      } finally {
        setLoading(false);
      }
    };

    fetchStats();
  }, []);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (query.trim()) {
      navigate(`/search?q=${encodeURIComponent(query.trim())}`);
    }
  };

  // Форматирование чисел (например, 1250 → 1.2K)
  const formatNumber = (num) => {
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
    if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
    return num.toString();
  };

  return (
    <div className="min-h-screen bg-[rgb(249,249,248)]" style={{ fontFamily: '"DM Sans", sans-serif' }}>
      {/* Header */}
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

      {/* Main content */}
      <main className="pt-14">
        <section className="overflow-hidden relative">
          {/* Градиентный фон */}
          <div className="pointer-events-none absolute left-0 top-0 right-0 bottom-0">
            <div
              className="pointer-events-none absolute w-[800px] h-[400px] left-1/2 top-0 blur-3xl -translate-x-1/2 opacity-[0.06] rounded-full"
              style={{
                backgroundImage: 'linear-gradient(135deg, rgb(30, 58, 95), rgb(45, 212, 168) 30%, rgb(168, 196, 157) 50%, rgb(232, 184, 74), rgb(255, 107, 53))'
              }}
            />
          </div>

          {/* Hero с поиском */}
          <div className="mx-auto relative w-full max-w-[1440px] pt-24 px-8 pb-16">
            <div className="mx-auto text-center max-w-3xl">
              {/* Бейдж */}
              <div className="inline-flex items-center font-medium text-center mb-6 bg-white border border-[rgb(232,228,222)] shadow-sm text-[rgba(44,44,44,0.6)]/60 text-xs gap-2 leading-4 py-1 px-3 rounded-full">
                <span className="block text-center w-1.5 h-1.5 bg-[rgb(45,212,168)] rounded-full" />
                Site Indexing &amp; Search
              </div>

              {/* Заголовок */}
              <h1
                className="font-semibold text-center mb-4 text-[rgb(19,19,19)] text-6xl tracking-[-1.5px] leading-[60px]"
                style={{ fontFamily: '"Space Grotesk", sans-serif' }}
              >
                Search your{' '}
                <span
                  className="bg-clip-text text-transparent"
                  style={{
                    backgroundImage: 'linear-gradient(135deg, rgb(30, 58, 95), rgb(45, 212, 168) 30%, rgb(168, 196, 157) 50%, rgb(232, 184, 74), rgb(255, 107, 53))'
                  }}
                >
                  indexed universe
                </span>
              </h1>

              {/* Описание */}
              <p className="mx-auto text-center mb-10 text-[rgba(44,44,44,0.6)]/60 text-lg leading-7 max-w-xl">
                Instantly search across all your indexed sites. Pulse crawls, indexes, and surfaces content with precision.
              </p>

              {/* Поисковая форма */}
              <div className="mx-auto text-center max-w-2xl">
                <form onSubmit={handleSubmit} className="text-center w-full">
                  <div className="flex items-center text-center bg-white border border-[rgb(232,228,222)] shadow-sm gap-3 py-4 px-5 rounded-[20px]">
                    <svg className="w-5 h-5 text-[rgba(44,44,44,0.4)]/40 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <circle cx="11" cy="11" r="8" strokeWidth="2" />
                      <path d="M21 21l-4.35-4.35" strokeWidth="2" strokeLinecap="round" />
                    </svg>
                    <input
                      type="text"
                      placeholder="Search sites, URLs, or content…"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      className="block grow overflow-clip bg-transparent text-[rgb(44,44,44)] outline-none basis-0"
                      autoFocus
                    />
                    <button
                      type="submit"
                      className="font-semibold text-center bg-[rgb(241,239,234)] text-[rgba(44,44,44,0.4)]/40 text-sm leading-5 py-2 px-5 shrink-0 rounded-xl transition-colors duration-200 hover:bg-[rgb(45,212,168)] hover:text-white cursor-pointer"
                    >
                      Search
                    </button>
                  </div>
                </form>
              </div>
            </div>
          </div>
        </section>

        <section className="bg-white border-t border-b border-[rgb(232,228,222)]">
          <div className="mx-auto w-full max-w-[1440px] py-4 px-8">
            <div className="grid grid-cols-4 gap-0">
              {/* Sites Indexed */}
              <div className="flex items-center gap-3 py-3 px-8">
                <svg className="w-5 h-5 text-[rgb(45,212,168)] shrink-0" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
                </svg>
                <div>
                  <p 
                    className="font-semibold text-[rgb(19,19,19)] text-xl leading-7"
                    style={{ fontFamily: '"Space Grotesk", sans-serif' }}
                  >
                    {loading ? "..." : formatNumber(stats.sites)}
                  </p>
                  <p className="text-[rgba(44,44,44,0.5)]/50 text-xs leading-4">Sites Indexed</p>
                </div>
              </div>

              {/* Pages Crawled */}
              <div className="flex items-center border-l border-[rgb(232,228,222)] gap-3 py-3 px-8">
                <svg className="w-5 h-5 text-[rgb(232,184,74)] shrink-0" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/>
                </svg>
                <div>
                  <p 
                    className="font-semibold text-[rgb(19,19,19)] text-xl leading-7"
                    style={{ fontFamily: '"Space Grotesk", sans-serif' }}
                  >
                    {loading ? "..." : formatNumber(stats.pages)}
                  </p>
                  <p className="text-[rgba(44,44,44,0.5)]/50 text-xs leading-4">Pages Crawled</p>
                </div>
              </div>

              {/* Last Sync */}
              <div className="flex items-center border-l border-[rgb(232,228,222)] gap-3 py-3 px-8">
                <svg className="w-5 h-5 text-[rgb(255,107,53)] shrink-0" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10 10-4.5 10-10S17.5 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm.5-13H11v6l5.2 3.2.8-1.3-4.5-2.7V7z"/>
                </svg>
                <div>
                  <p 
                    className="font-semibold text-[rgb(19,19,19)] text-xl leading-7"
                    style={{ fontFamily: '"Space Grotesk", sans-serif' }}
                  >
                    {loading ? "..." : stats.lastSync}
                  </p>
                  <p className="text-[rgba(44,44,44,0.5)]/50 text-xs leading-4">Last Sync</p>
                </div>
              </div>

              {/* Search Queries */}
              <div className="flex items-center border-l border-[rgb(232,228,222)] gap-3 py-3 px-8">
                <svg className="w-5 h-5 text-[rgb(30,58,95)] shrink-0" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M3 13h2v-2H3v2zm0 4h2v-2H3v2zm0-8h2V7H3v2zm4 4h14v-2H7v2zm0 4h14v-2H7v2zM7 7v2h14V7H7z"/>
                </svg>
                <div>
                  <p 
                    className="font-semibold text-[rgb(19,19,19)] text-xl leading-7"
                    style={{ fontFamily: '"Space Grotesk", sans-serif' }}
                  >
                    {loading ? "..." : formatNumber(stats.queries)}
                  </p>
                  <p className="text-[rgba(44,44,44,0.5)]/50 text-xs leading-4">Search Queries</p>
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}

export default HomePage;
