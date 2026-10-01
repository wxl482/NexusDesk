import { createRouter, createWebHashHistory } from 'vue-router'
import ChatView from '../views/ChatView.vue'
import RagView from '../views/RagView.vue'
import ToolsView from '../views/ToolsView.vue'
import SettingsView from '../views/SettingsView.vue'

const routes = [
  {
    path: '/',
    name: 'chat',
    component: ChatView,
  },
  {
    path: '/rag',
    name: 'rag',
    component: RagView,
  },
  {
    path: '/tools',
    name: 'tools',
    component: ToolsView,
  },

  {
    path: '/settings',
    name: 'settings',
    component: SettingsView,
  },
  {
    path: '/quick-bar',
    name: 'quick-bar',
    component: () => import('../views/QuickBarView.vue'),
  },
]

export const router = createRouter({
  history: createWebHashHistory(),
  routes,
})
