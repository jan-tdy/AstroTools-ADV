## What it does

Reads and writes tables as HDF5 or Parquet, converts workspace objects to and from YAML text and ASDF files, and lists all table formats registered in astropy.

## How to use

- **Tables.** Select a workspace **Table**, a **File**, **Format** (`hdf5` or `parquet`) and for HDF5 the **HDF5 path** (default `data`). **Serialize meta (HDF5)** keeps metadata, **Append (HDF5)** adds to an existing file, **Overwrite** replaces it. **Write** saves; **Read** loads into the workspace under **Store as** (default `misc_table`).
- **YAML.** Choose a **Workspace object** and press **Object -> YAML text**; edit the **YAML text** and press **YAML text -> workspace** (**Store as** `yaml_object`). **Save YAML text to file** and **Load YAML file -> workspace** use files. YAML handles Quantity, Time, SkyCoord and units.
- **ASDF.** **Object -> ASDF file** and **ASDF file -> workspace**.

## Reading the results

**Dependencies** shows which optional packages (`h5py` for HDF5, `pyarrow` for Parquet, `asdf`, `pyyaml`) are installed; use of a format whose package is missing is reported in **Messages**. **All table formats** lists format names with read and write support.

## Tips and limits

- HDF5 stores astropy units and metadata when **Serialize meta** is on; Parquet keeps column data and units but little metadata.
- One HDF5 file can hold several tables under different paths.
