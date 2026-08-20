import math
from typing import TypeVar, Generic, List, Tuple, Dict, Set, Callable

T = TypeVar('T')

class SpatialGrid(Generic[T]):
    """
    Buckets items into a 2D grid to reduce collision detection from O(N^2) to O(N).
    """
    def __init__(self, cell_size: float):
        # Prevent division by zero; default to a reasonable minimum cell size
        self.cell_size = max(1.0, cell_size)
        self.grid: Dict[Tuple[int, int], List[T]] = {}

    def _get_cells(self, box: tuple) -> List[Tuple[int, int]]:
        """Calculates all grid cell coordinates that a bounding box overlaps."""
        min_x, max_x, min_y, max_y = box
        min_col = int(math.floor(min_x / self.cell_size))
        max_col = int(math.floor(max_x / self.cell_size))
        min_row = int(math.floor(min_y / self.cell_size))
        max_row = int(math.floor(max_y / self.cell_size))
        
        cells = []
        for r in range(min_row, max_row + 1):
            for c in range(min_col, max_col + 1):
                cells.append((r, c))
        return cells

    def add(self, item: T, box: tuple) -> None:
        """Inserts an item into all cells its bounding box touches."""
        for cell in self._get_cells(box):
            if cell not in self.grid:
                self.grid[cell] = []
            self.grid[cell].append(item)

    def get_potential_neighbors(self, box: tuple) -> Set[T]:
        """Retrieves all unique items sharing a grid cell with the given box."""
        neighbors = set()
        for cell in self._get_cells(box):
            if cell in self.grid:
                neighbors.update(self.grid[cell])
        return neighbors

    def cluster_spatially(
        items: List[T], 
        get_bbox_fn: Callable[[T], tuple], 
        is_touching_fn: Callable[[T, T], bool], 
        threshold: float
    ) -> List[List[T]]:
        """
        Groups items using a spatial grid to find connected components efficiently.
        
        Args:
            items: List of objects to cluster (e.g., Strokes or Features).
            get_bbox_fn: Function that returns (min_x, max_x, min_y, max_y) for an item.
            is_touching_fn: Detailed boolean check to confirm if two items merge.
            threshold: The maximum gap distance allowed for items to be considered touching.
        """
        if not items:
            return []

        # 1. Initialize the grid. Set cell size to the threshold.
        cell_size = max(threshold, 10.0) 
        grid = SpatialGrid[T](cell_size)
        
        # 2. Populate the grid with expanded bounding boxes
        item_boxes = {}
        for item in items:
            min_x, max_x, min_y, max_y = get_bbox_fn(item)
            # Expand the box by the threshold so overlaps guarantee they are close enough
            expanded_box = (
                min_x - threshold, 
                max_x + threshold, 
                min_y - threshold, 
                max_y + threshold
            )
            item_boxes[item] = expanded_box
            grid.add(item, expanded_box)

        # 3. Find connected components using BFS
        visited: Set[T] = set()
        clusters: List[List[T]] = []

        for item in items:
            if item in visited:
                continue

            # Start a new cluster group
            current_cluster = []
            queue = [item]
            visited.add(item)

            while queue:
                current = queue.pop(0)
                current_cluster.append(current)
                
                # Fast Path: Only check items in overlapping grid cells
                potential_neighbors = grid.get_potential_neighbors(item_boxes[current])
                
                for neighbor in potential_neighbors:
                    if neighbor not in visited:
                        # Slow Path: Perform the actual, accurate geometric check
                        if is_touching_fn(current, neighbor):
                            visited.add(neighbor)
                            queue.append(neighbor)
            
            clusters.append(current_cluster)
            
        return clusters