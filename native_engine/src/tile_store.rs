//! LRU tile store with byte-budget eviction.
//!
//! Tiles are cached by `(layer_id, tile_x, tile_y, mip_level)`.  When the
//! total byte budget is exceeded, the least-recently-used tiles are evicted.
//!
//! This replaces the Python `dict`-based tile cache with a memory-bounded,
//! cache-friendly Rust implementation.

use lru::LruCache;
use std::num::NonZeroUsize;

#[derive(Clone, Debug, Hash, PartialEq, Eq)]
pub struct TileKey {
    pub layer_id: u64,
    pub tx: u32,
    pub ty: u32,
    pub mip: u8,
}

pub struct TileData {
    pub pixels: Vec<f32>,
    pub width: u32,
    pub height: u32,
}

impl TileData {
    pub fn byte_size(&self) -> usize {
        self.pixels.len() * std::mem::size_of::<f32>()
    }
}

pub struct TileStore {
    cache: LruCache<TileKey, TileData>,
    byte_budget: usize,
    current_bytes: usize,
}

impl TileStore {
    pub fn new(byte_budget: usize, max_tiles: usize) -> Self {
        Self {
            cache: LruCache::new(
                NonZeroUsize::new(max_tiles).unwrap_or(NonZeroUsize::new(4096).unwrap()),
            ),
            byte_budget,
            current_bytes: 0,
        }
    }

    pub fn get(&mut self, key: &TileKey) -> Option<&TileData> {
        self.cache.get(key)
    }

    pub fn put(&mut self, key: TileKey, data: TileData) {
        let new_bytes = data.byte_size();

        // Evict old entry for same key if present
        if let Some(old) = self.cache.pop(&key) {
            self.current_bytes -= old.byte_size();
        }

        // Evict LRU tiles until budget allows the new tile
        while self.current_bytes + new_bytes > self.byte_budget {
            if let Some((_, evicted)) = self.cache.pop_lru() {
                self.current_bytes -= evicted.byte_size();
            } else {
                break;
            }
        }

        self.current_bytes += new_bytes;
        self.cache.put(key, data);
    }

    pub fn invalidate(&mut self, key: &TileKey) {
        if let Some(removed) = self.cache.pop(key) {
            self.current_bytes -= removed.byte_size();
        }
    }

    pub fn invalidate_layer(&mut self, layer_id: u64) {
        let keys: Vec<TileKey> = self.cache
            .iter()
            .filter(|(k, _)| k.layer_id == layer_id)
            .map(|(k, _)| k.clone())
            .collect();
        for k in keys {
            if let Some(removed) = self.cache.pop(&k) {
                self.current_bytes -= removed.byte_size();
            }
        }
    }

    pub fn clear(&mut self) {
        self.cache.clear();
        self.current_bytes = 0;
    }

    pub fn len(&self) -> usize {
        self.cache.len()
    }

    pub fn current_bytes(&self) -> usize {
        self.current_bytes
    }

    pub fn byte_budget(&self) -> usize {
        self.byte_budget
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_tile(size: usize) -> TileData {
        TileData {
            pixels: vec![0.0; size],
            width: 256,
            height: 256,
        }
    }

    #[test]
    fn test_put_get() {
        let mut store = TileStore::new(1024 * 1024, 100);
        let key = TileKey { layer_id: 1, tx: 0, ty: 0, mip: 0 };
        store.put(key.clone(), make_tile(256 * 256 * 4));
        assert!(store.get(&key).is_some());
    }

    #[test]
    fn test_eviction() {
        // Budget for ~2 tiles
        let tile_bytes = 256 * 256 * 4 * 4; // 1 MiB per tile
        let mut store = TileStore::new(tile_bytes * 2 + 100, 100);

        let k1 = TileKey { layer_id: 1, tx: 0, ty: 0, mip: 0 };
        let k2 = TileKey { layer_id: 1, tx: 1, ty: 0, mip: 0 };
        let k3 = TileKey { layer_id: 1, tx: 2, ty: 0, mip: 0 };

        store.put(k1.clone(), make_tile(256 * 256 * 4));
        store.put(k2.clone(), make_tile(256 * 256 * 4));
        assert_eq!(store.len(), 2);

        // Adding a 3rd tile should evict k1 (LRU)
        store.put(k3.clone(), make_tile(256 * 256 * 4));
        assert!(store.get(&k1).is_none());
        assert!(store.get(&k3).is_some());
    }

    #[test]
    fn test_invalidate_layer() {
        let mut store = TileStore::new(10 * 1024 * 1024, 100);
        let k1 = TileKey { layer_id: 1, tx: 0, ty: 0, mip: 0 };
        let k2 = TileKey { layer_id: 1, tx: 1, ty: 0, mip: 0 };
        let k3 = TileKey { layer_id: 2, tx: 0, ty: 0, mip: 0 };

        store.put(k1, make_tile(100));
        store.put(k2, make_tile(100));
        store.put(k3.clone(), make_tile(100));
        assert_eq!(store.len(), 3);

        store.invalidate_layer(1);
        assert_eq!(store.len(), 1);
        assert!(store.get(&k3).is_some());
    }
}
