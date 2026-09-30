`stayfixed init` no longer glues its `.gitignore` region onto a last line that ends in a lone
carriage return. git ends a line only at a newline, so it read your last pattern and the region's
first line as one pattern, and your pattern stopped hiding anything.
