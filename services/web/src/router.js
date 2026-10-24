import { createRouter, createWebHashHistory } from "vue-router";
import { auth } from "./api.js";

// Hash history: StaticFiles(html=True) di /ui tidak punya fallback SPA, dan fragmen tidak terkirim ke server/log.
export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: "/login", component: () => import("./views/LoginView.vue"), meta: { public: true } },
    { path: "/", redirect: "/queue" },
    { path: "/queue", component: () => import("./views/QueueView.vue") },
    { path: "/history", component: () => import("./views/HistoryView.vue") },
    { path: "/session/:id", component: () => import("./views/SessionView.vue") },
    { path: "/admin/:page", component: () => import("./views/AdminView.vue") },
    { path: "/:rest(.*)*", redirect: "/queue" },
  ],
});

router.beforeEach((to) => {
  if (!to.meta.public && !auth.token) return { path: "/login", query: to.fullPath !== "/queue" ? { next: to.fullPath } : {} };
  if (to.path === "/login" && auth.token) return "/queue";
});
