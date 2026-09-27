<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { darkTheme, NConfigProvider, NMessageProvider, NDialogProvider } from 'naive-ui'
import { useSettingsStore } from './stores/settings'
import AppLayout from './components/AppLayout.vue'

const settingsStore = useSettingsStore()

const currentTheme = computed(() => {
  return settingsStore.isDark ? darkTheme : null
})

onMounted(() => {
  if (settingsStore.isDark) {
    document.documentElement.classList.add('dark')
  } else {
    document.documentElement.classList.remove('dark')
  }
})
</script>

<template>
  <NConfigProvider :theme="currentTheme">
    <NMessageProvider>
      <NDialogProvider>
        <AppLayout />
      </NDialogProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>
