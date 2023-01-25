# l10n Tools
Various tools relating to l10n. 

If you're using Mac we recommend using [CoreUtils](https://formulae.brew.sh/formula/coreutils) and [FindUtils](https://formulae.brew.sh/formula/findutils) to ensure the bash scripts work correctly.

## Extraction
From this directory simply run:
`./extract.sh`

If you receive errors similar to: `mv: illegal option -t` or `find: -printf: unknown primary or operator`, then please see the above disclaimer about CoreUtils/FindUtils. You may need to temporarily modify the script to use `gmv`/`gfind`.  
