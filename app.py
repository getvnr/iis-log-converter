import streamlit as st
import pandas as pd
from io import BytesIO
import datetime
import re

# Ensure openpyxl is available
try:
    import openpyxl
except ImportError:
    st.error("The 'openpyxl' library is not installed. Please ensure it is included in your environment (e.g., via requirements.txt).")
    st.stop()

def parse_iis_log(file_content):
    try:
        lines = file_content.decode('utf-8', errors='ignore').splitlines()
        fields = None
        data = []
        
        for line in lines:
            if line.startswith('#'):
                if line.startswith('#Fields:'):
                    fields = line.split()[1:]
                continue
            if fields and line.strip():
                row = line.split()
                if len(row) == len(fields):
                    data.append(row)
        
        if not fields or not data:
            raise ValueError("Invalid IIS log format or no data found")
        
        df = pd.DataFrame(data, columns=fields)
        
        # Convert relevant columns to numeric
        numeric_cols = ['s-port', 'sc-status', 'sc-substatus', 'sc-win32-status', 'sc-bytes', 'cs-bytes', 'time-taken']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Combine date and time into datetime if present
        if 'date' in df.columns and 'time' in df.columns:
            df['datetime'] = pd.to_datetime(df['date'] + ' ' + df['time'], errors='coerce')
        
        return df
    except Exception as e:
        raise ValueError(f"Error parsing log file: {str(e)}")

def generate_summary(df):
    try:
        if 'sc-status' not in df.columns or 'time-taken' not in df.columns:
            raise ValueError("Required columns 'sc-status' or 'time-taken' not found in log data")
        
        summary = df.groupby('sc-status').agg(
            count=('sc-status', 'size'),
            avg_time_taken=('time-taken', 'mean'),
            max_time_taken=('time-taken', 'max'),
            min_time_taken=('time-taken', 'min')
        ).reset_index()
        
        summary.columns = ['sc_status', 'count', 'avg_time_taken', 'max_time_taken', 'min_time_taken']
        return summary
    except Exception as e:
        raise ValueError(f"Error generating summary: {str(e)}")

def create_xlsx(summary_df, raw_df):
    try:
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            summary_df.to_excel(writer, sheet_name='StatusSummary', index=False)
            raw_df.to_excel(writer, sheet_name='RawData', index=False)
        output.seek(0)
        return output
    except Exception as e:
        raise ValueError(f"Error creating XLSX file: {str(e)}")

st.title("IIS Log to XLSX Converter")

uploaded_file = st.file_uploader("Upload IIS .log file", type=["log"])

if uploaded_file:
    try:
        file_content = uploaded_file.read()
        raw_df = parse_iis_log(file_content)
        summary_df = generate_summary(raw_df)
        
        xlsx_output = create_xlsx(summary_df, raw_df)
        
        st.success("File processed successfully!")
        
        st.download_button(
            label="Download XLSX",
            data=xlsx_output,
            file_name="IIS_log_summary.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        st.subheader("Preview of Status Summary")
        st.dataframe(summary_df)
        
        st.subheader("Preview of Raw Data (first 10 rows)")
        st.dataframe(raw_df.head(10))
        
    except Exception as e:
        st.error(f"Error processing file: {str(e)}")
