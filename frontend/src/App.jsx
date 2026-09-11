import {
  useEffect,
  useRef,
  useState,
} from "react";

import {
  AlertTriangle,
  Bell,
  CheckCircle2,
  ChevronDown,
  Clock,
  LayoutDashboard,
  Leaf,
  Menu,
  Moon,
  Satellite,
  Search,
  Settings,
  ShieldCheck,
  Sun,
  TreePine,
  X,
} from "lucide-react";

import Analysis from "./pages/Analysis";
import Alerts from "./pages/Alerts";
import Dashboard from "./pages/Dashboard";
import Detections from "./pages/Detections";
import ForestAreaDetails from "./pages/ForestAreaDetails";
import ForestAreas from "./pages/ForestAreas";
import Login from "./pages/Login";
import RegisterForestArea from "./pages/RegisterForestArea";
import SatelliteImages from "./pages/SatelliteImages";
import SettingsPage from "./pages/Settings";

const API_URL = "http://127.0.0.1:8000";

function App() {
  const [isAuthenticated, setIsAuthenticated] =
    useState(false);

  const [darkMode, setDarkMode] =
    useState(false);

  const [sidebarOpen, setSidebarOpen] =
    useState(true);

  const [activePage, setActivePage] =
    useState("Dashboard");

  const [selectedForestId, setSelectedForestId] =
    useState(null);

  const [notifications, setNotifications] =
    useState([]);

  const [notificationOpen, setNotificationOpen] =
    useState(false);

  const [notificationLoading, setNotificationLoading] =
    useState(false);

  const [readNotificationIds, setReadNotificationIds] =
    useState(() => {
      try {
        const saved = localStorage.getItem(
          "forestwatch_read_notifications"
        );

        return saved ? JSON.parse(saved) : [];
      } catch {
        return [];
      }
    });

  const notificationRef = useRef(null);

  const navigation = [
    {
      name: "Dashboard",
      icon: LayoutDashboard,
    },
    {
      name: "Forest Areas",
      icon: TreePine,
    },
    {
      name: "Analysis",
      icon: Satellite,
    },
    {
      name: "Detections",
      icon: Leaf,
    },
    {
      name: "Alerts",
      icon: Bell,
    },
    {
      name: "Satellite Images",
      icon: Satellite,
    },
  ];

  useEffect(() => {
    localStorage.setItem(
      "forestwatch_read_notifications",
      JSON.stringify(readNotificationIds)
    );
  }, [readNotificationIds]);

  const fetchNotifications = async () => {
    try {
      setNotificationLoading(true);

      const token =
        localStorage.getItem("access_token") ||
        localStorage.getItem("token");

      if (!token) {
        return;
      }

      const response = await fetch(
        `${API_URL}/api/v1/alerts`,
        {
          method: "GET",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) {
        throw new Error(
          `Unable to load notifications. Server returned ${response.status}.`
        );
      }

      const data = await response.json();

      const alerts = Array.isArray(data)
        ? data
        : [];

      setNotifications(alerts);

      const backendReadIds = alerts
        .filter(
          (alert) => alert.is_read === true
        )
        .map((alert) => alert.id);

      if (backendReadIds.length > 0) {
        setReadNotificationIds((current) => [
          ...new Set([
            ...current,
            ...backendReadIds,
          ]),
        ]);
      }
    } catch (error) {
      console.error(
        "Notification Error:",
        error
      );
    } finally {
      setNotificationLoading(false);
    }
  };

  const markNotificationAsRead = async (
    alertId
  ) => {
    try {
      const token =
        localStorage.getItem("access_token") ||
        localStorage.getItem("token");

      if (!token) {
        return;
      }

      setReadNotificationIds((current) => [
        ...new Set([
          ...current,
          alertId,
        ]),
      ]);

      const response = await fetch(
        `${API_URL}/api/v1/alerts/${alertId}/read`,
        {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) {
        console.error(
          `Failed to mark alert ${alertId} as read.`
        );
      }
    } catch (error) {
      console.error(
        "Mark notification as read error:",
        error
      );
    }
  };

  useEffect(() => {
    if (isAuthenticated) {
      fetchNotifications();
    }
  }, [isAuthenticated]);

  useEffect(() => {
    if (!isAuthenticated) {
      return;
    }

    const interval = setInterval(() => {
      fetchNotifications();
    }, 60000);

    return () => {
      clearInterval(interval);
    };
  }, [isAuthenticated]);

  useEffect(() => {
    const handleOutsideClick = (event) => {
      if (
        notificationRef.current &&
        !notificationRef.current.contains(
          event.target
        )
      ) {
        setNotificationOpen(false);
      }
    };

    document.addEventListener(
      "mousedown",
      handleOutsideClick
    );

    return () => {
      document.removeEventListener(
        "mousedown",
        handleOutsideClick
      );
    };
  }, []);

  const unreadNotifications =
    notifications.filter((notification) => {
      const isRead =
        notification.is_read === true ||
        readNotificationIds.includes(
          notification.id
        );

      const isResolved =
        notification.is_resolved === true ||
        notification.status === "RESOLVED";

      return !isRead && !isResolved;
    });

  const formatNotificationDate = (date) => {
    if (!date) {
      return "";
    }

    try {
      return new Date(date).toLocaleString(
        "en-ZM",
        {
          day: "2-digit",
          month: "short",
          hour: "2-digit",
          minute: "2-digit",
        }
      );
    } catch {
      return "";
    }
  };

  const getPriorityClass = (priority) => {
    const value = String(
      priority || ""
    ).toLowerCase();

    if (value === "critical") {
      return "notification-priority critical";
    }

    if (value === "high") {
      return "notification-priority high";
    }

    if (value === "medium") {
      return "notification-priority medium";
    }

    return "notification-priority low";
  };

  if (!isAuthenticated) {
    return (
      <Login
        onLogin={() => {
          setIsAuthenticated(true);
          setActivePage("Dashboard");
          setSelectedForestId(null);
        }}
      />
    );
  }

  return (
    <div className={darkMode ? "app dark" : "app"}>

      <aside
        className={`sidebar ${
          sidebarOpen ? "open" : "closed"
        }`}
      >
        <div className="brand">
          <div className="brand-mark">
            <TreePine
              size={24}
              strokeWidth={2.2}
            />
          </div>

          {sidebarOpen && (
            <div className="brand-text">
              <strong>
                ForestWatch
              </strong>

              <span>
                ZAMBIA
              </span>
            </div>
          )}

          {sidebarOpen && (
            <button
              className="mobile-close"
              onClick={() =>
                setSidebarOpen(false)
              }
              aria-label="Close sidebar"
            >
              <X size={20} />
            </button>
          )}
        </div>

        <div className="sidebar-section">
          {sidebarOpen && (
            <p className="section-label">
              MONITORING
            </p>
          )}

          <nav>
            {navigation.map((item) => {
              const Icon = item.icon;

              return (
                <button
                  key={item.name}
                  className={`nav-item ${
                    activePage === item.name
                      ? "active"
                      : ""
                  }`}
                  onClick={() => {
                    setActivePage(
                      item.name
                    );

                    if (
                      item.name !==
                      "Forest Areas"
                    ) {
                      setSelectedForestId(
                        null
                      );
                    }
                  }}
                >
                  <Icon size={20} />

                  {sidebarOpen && (
                    <span>
                      {item.name}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>
        </div>

        <div className="sidebar-bottom">
          <button
            className={`nav-item ${
              activePage === "Settings"
                ? "active"
                : ""
            }`}
            onClick={() => {
              setActivePage("Settings");
              setSelectedForestId(null);
            }}
          >
            <Settings size={20} />

            {sidebarOpen && (
              <span>
                Settings
              </span>
            )}
          </button>

          {sidebarOpen && (
            <div className="institution-card">
              <ShieldCheck size={20} />

              <div>
                <strong>
                  Zambia University
                </strong>

                <span>
                  College of Technology
                </span>
              </div>
            </div>
          )}
        </div>
      </aside>

      <div className="main-area">

        <header className="topbar">
          <div className="topbar-left">

            <button
              className="icon-button"
              onClick={() =>
                setSidebarOpen(
                  !sidebarOpen
                )
              }
              aria-label="Toggle sidebar"
            >
              <Menu size={21} />
            </button>

            <div className="breadcrumb">
              <span>
                ForestWatch Zambia
              </span>

              <strong>
                /
              </strong>

              <span className="current">
                {activePage}
              </span>
            </div>
          </div>

          <div className="topbar-right">

            <div className="search-box">
              <Search size={18} />

              <input
                type="search"
                placeholder="Search..."
                aria-label="Search"
              />
            </div>

            <button
              className="icon-button"
              onClick={() =>
                setDarkMode(!darkMode)
              }
              aria-label="Toggle theme"
            >
              {darkMode ? (
                <Sun size={20} />
              ) : (
                <Moon size={20} />
              )}
            </button>

            <div
              className="notification-wrapper"
              ref={notificationRef}
            >
              <button
                className={`notification-button ${
                  notificationOpen
                    ? "notification-active"
                    : ""
                }`}
                onClick={() => {
                  const opening =
                    !notificationOpen;

                  setNotificationOpen(
                    opening
                  );

                  if (opening) {
                    fetchNotifications();
                  }
                }}
                title="Notifications"
                aria-label="Notifications"
              >
                <Bell size={20} />

                {unreadNotifications.length >
                  0 && (
                  <span className="notification-count">
                    {unreadNotifications.length >
                    9
                      ? "9+"
                      : unreadNotifications.length}
                  </span>
                )}
              </button>

              {notificationOpen && (
                <div className="notification-panel">

                  <div className="notification-panel-header">
                    <div>
                      <h3>
                        Notifications
                      </h3>

                      <span>
                        Forest monitoring alerts
                      </span>
                    </div>

                    <button
                      className="notification-refresh"
                      onClick={
                        fetchNotifications
                      }
                      aria-label="Refresh notifications"
                    >
                      ↻
                    </button>
                  </div>

                  <div className="notification-list">

                    {notificationLoading && (
                      <div className="notification-empty">
                        <div className="notification-spinner">
                          ⟳
                        </div>

                        <p>
                          Loading alerts...
                        </p>
                      </div>
                    )}

                    {!notificationLoading &&
                      notifications.length ===
                        0 && (
                        <div className="notification-empty">
                          <Bell size={28} />

                          <strong>
                            No notifications
                          </strong>

                          <p>
                            There are currently no
                            forest monitoring alerts.
                          </p>
                        </div>
                    )}

                    {!notificationLoading &&
                      notifications
                        .slice(0, 5)
                        .map(
                          (
                            notification
                          ) => {
                            const isRead =
                              notification.is_read ===
                                true ||
                              readNotificationIds.includes(
                                notification.id
                              );

                            return (
                              <div
                                className={`notification-item ${
                                  notification.is_resolved
                                    ? "resolved"
                                    : ""
                                } ${
                                  isRead
                                    ? "notification-read"
                                    : "notification-unread"
                                }`}
                                key={
                                  notification.id
                                }
                                onClick={() => {
                                  if (!isRead) {
                                    markNotificationAsRead(
                                      notification.id
                                    );
                                  }
                                }}
                              >
                                <div className="notification-item-icon">
                                  {notification.priority ===
                                  "CRITICAL" ? (
                                    <AlertTriangle
                                      size={18}
                                    />
                                  ) : notification.is_resolved ? (
                                    <CheckCircle2
                                      size={18}
                                    />
                                  ) : (
                                    <Bell
                                      size={18}
                                    />
                                  )}
                                </div>

                                <div className="notification-item-content">
                                  <div className="notification-title-row">
                                    <strong>
                                      {
                                        notification.title
                                      }
                                    </strong>

                                    <span
                                      className={getPriorityClass(
                                        notification.priority
                                      )}
                                    >
                                      {
                                        notification.priority
                                      }
                                    </span>
                                  </div>

                                  <p>
                                    {
                                      notification.message
                                    }
                                  </p>

                                  <div className="notification-meta">
                                    <span>
                                      <Clock
                                        size={13}
                                      />

                                      {formatNotificationDate(
                                        notification.created_at
                                      )}
                                    </span>

                                    {notification.is_resolved && (
                                      <span className="notification-resolved">
                                        Resolved
                                      </span>
                                    )}

                                    {isRead && (
                                      <span className="notification-read-label">
                                        Read
                                      </span>
                                    )}
                                  </div>
                                </div>
                              </div>
                            );
                          }
                        )}
                  </div>

                  <div className="notification-panel-footer">
                    <span>
                      {
                        unreadNotifications.length
                      }{" "}
                      unread
                    </span>

                    <button
                      onClick={() =>
                        setNotificationOpen(
                          false
                        )
                      }
                    >
                      Close
                    </button>
                  </div>
                </div>
              )}
            </div>

            <div className="user-profile">
              <div className="avatar">
                FO
              </div>

              <div className="user-details">
                <strong>
                  Forestry Officer
                </strong>

                <span>
                  Forest Monitoring
                </span>
              </div>

              <ChevronDown size={17} />
            </div>
          </div>
        </header>

        <main className="content">

          {activePage === "Dashboard" && (
            <Dashboard />
          )}

          {activePage === "Analysis" && (
            <Analysis />
          )}

          {activePage === "Forest Areas" && (
            <ForestAreas
              onRegister={() => {
                setSelectedForestId(null);
                setActivePage(
                  "Register Forest Area"
                );
              }}
              onViewDetails={(forestId) => {
                setSelectedForestId(
                  forestId
                );

                setActivePage(
                  "Forest Area Details"
                );
              }}
            />
          )}

          {activePage ===
            "Register Forest Area" && (
            <RegisterForestArea
              onBack={() => {
                setActivePage(
                  "Forest Areas"
                );
              }}
              onRegistered={() => {
                setSelectedForestId(null);
                setActivePage(
                  "Forest Areas"
                );
              }}
            />
          )}

          {activePage ===
            "Forest Area Details" && (
            <ForestAreaDetails
              forestId={
                selectedForestId
              }
              onBack={() => {
                setSelectedForestId(null);
                setActivePage(
                  "Forest Areas"
                );
              }}
            />
          )}

          {activePage === "Detections" && (
            <Detections />
          )}

          {activePage === "Alerts" && (
            <Alerts />
          )}

          {activePage ===
            "Satellite Images" && (
            <SatelliteImages />
          )}

          {activePage === "Settings" && (
            <SettingsPage />
          )}
        </main>

        <footer className="footer">
          <span>
            ForestWatch Zambia
          </span>

          <span>
            •
          </span>

          <span>
            Zambia University College
            of Technology
          </span>

          <span>
            •
          </span>

          <span>
            Intelligent Forest Monitoring
          </span>
        </footer>
      </div>
    </div>
  );
}

export default App;