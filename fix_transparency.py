import os
from PIL import Image, ImageDraw
import numpy as np

ICONS_DIR = r"c:\Users\stati\Desktop\Projects\AlphaHoundGUI\backend\static\icons"

def remove_background_floodfill(image_path):
    print(f"Processing {image_path}...")
    try:
        img = Image.open(image_path).convert("RGBA")
        width, height = img.size
        
        # Get background color sample from corners
        corners = [
            (0, 0),
            (width-1, 0),
            (0, height-1),
            (width-1, height-1)
        ]
        
        # Use ImageDraw.floodfill to make background transparent
        # We need a seed point. We'll assume at least one corner is background.
        # But floodfill on RGBA works best if we first identify the region.
        
        # Alternative approach:
        # Create a mask image initialized to 0
        mask = Image.new('L', (width, height), 0)
        
        # We will use the 'tolerance' parameter of floodfill if we implemented it manually, 
        # but PIL's floodfill fills a color.
        
        # Let's try a different strategy:
        # 1. Identify the background color (most frequent corner color)
        # 2. Compute difference from this color
        # 3. Use flood fill on the difference map to find the connected background region
        
        data = np.array(img)
        
        # Get corner colors
        corner_colors = [tuple(data[y, x]) for x, y in corners]
        # Find most common corner color (simple count)
        bg_color = max(set(corner_colors), key=corner_colors.count)
        
        # Calculate Euclidean distance from bg_color
        diff = np.sqrt(np.sum((data - bg_color) ** 2, axis=2))
        
        # Threshold: pixels close to background color are candidates
        # Tolerance of 25 (approx 10% for individual channels combined)
        candidates = diff < 25
        
        # Now we only want candidates connected to the edge (flood fill approach)
        # We can implement a simple BFS/DFS on the boolean mask
        
        processed_mask = np.zeros(candidates.shape, dtype=bool)
        queue = []
        
        # Add all border pixels that are candidates to the queue
        for x in range(width):
            if candidates[0, x]: queue.append((0, x))
            if candidates[height-1, x]: queue.append((height-1, x))
            
        for y in range(height):
            if candidates[y, 0]: queue.append((y, 0))
            if candidates[y, width-1]: queue.append((y, width-1))
            
        # Standard BFS
        while queue:
            y, x = queue.pop(0)
            if processed_mask[y, x]:
                continue
            
            processed_mask[y, x] = True
            
            # Check neighbors
            for dy, dx in [(-1,0), (1,0), (0,-1), (0,1)]:
                ny, nx = y + dy, x + dx
                if 0 <= ny < height and 0 <= nx < width:
                    if candidates[ny, nx] and not processed_mask[ny, nx]:
                        queue.append((ny, nx))
        
        # processed_mask now contains True for background pixels
        
        # Set alpha to 0 for these pixels
        data[..., 3][processed_mask] = 0
        
        new_img = Image.fromarray(data)
        new_img.save(image_path, "PNG")
        print(f"Saved {image_path} (Corner color: {bg_color})")
        
    except Exception as e:
        print(f"Failed to process {image_path}: {e}")

if __name__ == "__main__":
    if not os.path.exists(ICONS_DIR):
        print(f"Directory not found: {ICONS_DIR}")
    else:
        for filename in os.listdir(ICONS_DIR):
            if filename.lower().endswith(".png"):
                remove_background_floodfill(os.path.join(ICONS_DIR, filename))
