import pandas as pd
import plotly.graph_objects as go
import re
import streamlit as st
import time
from datetime import datetime
from easysnmp import Session


def get_snmp_session(ip, community, version):
    return Session(hostname=ip, community=community, version=version)


def get_interfaces(session):
    interface_names = session.walk("1.3.6.1.2.1.2.2.1.2")
    interface_descriptions = session.walk("1.3.6.1.2.1.31.1.1.1.18")
    interfaces = {}
    name_map = {int(item.oid.split('.')[-1]): item.value for item in interface_names}
    desc_map = {int(item.oid.split('.')[-1]): item.value for item in interface_descriptions}
    for index, name in name_map.items():
        description = desc_map.get(index, "").strip()
        interfaces[index] = f"{name} ({description})" if description else name
    return interfaces


def get_traffic_in_out(session, index):
    oids = [
        f"1.3.6.1.2.1.31.1.1.1.6.{index}",
        f"1.3.6.1.2.1.31.1.1.1.10.{index}"
    ]
    result = session.get(oids)
    oct_in = int(result[0].value)
    oct_out = int(result[1].value)
    return oct_in, oct_out


def is_valid_ip(ip_address):
    pattern = r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$"
    if not re.match(pattern, ip_address):
        return False
    return all(0 <= int(part) <= 255 for part in ip_address.split('.'))


def plot_graph(df, monitor_in, monitor_out, chart_container):
    if df.empty:
        st.info("Sem dados suficientes para exibir o gráfico.")
        return

    # Determina se a unidade será Mbps ou Gbps
    max_val = max(
        df["in"].max() if monitor_in else 0,
        df["out"].max() if monitor_out else 0
    )

    if max_val >= 1000:
        unit = "Gbps"
        factor = 1000
    else:
        unit = "Mbps"
        factor = 1

    if monitor_in:
        df["in_display"] = df["in"] / factor
    if monitor_out:
        df["out_display"] = df["out"] / factor

    # Gráfico
    fig = go.Figure()

    if monitor_in:
        fig.add_trace(go.Scatter(
            x=df["timestamp"],
            y=df["in_display"],
            mode="lines+markers",
            name=f"Entrada ({unit})",
            line=dict(color="#47A8DE", width=2),
            marker=dict(color="#47A8DE")
        ))

    if monitor_out:
        fig.add_trace(go.Scatter(
            x=df["timestamp"],
            y=df["out_display"],
            mode="lines+markers",
            name=f"Saída ({unit})",
            line=dict(color="#D6008D", width=2),
            marker=dict(color="#D6008D")
        ))

    fig.update_layout(
        title="Tráfego em tempo real",
        xaxis_title="Horário",
        yaxis_title=unit,
        legend_title="Direção",
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='white'),
        title_font=dict(color='white'),
        legend=dict(font=dict(color='white')),
        xaxis=dict(color='white'),
        yaxis=dict(color='white', rangemode='tozero'),
    )

    chart_container.plotly_chart(fig, use_container_width=True)

    # Estatísticas
    col1, col2, col3 = st.columns(3)

    if monitor_in:
        col1.metric("Entrada Máx", f"{df['in_display'].max():.2f} {unit}")
        col2.metric("Entrada Mín", f"{df['in_display'].min():.2f} {unit}")
        col3.metric("Última Entrada", f"{df['in_display'].iloc[-1]:.2f} {unit}")

    if monitor_out:
        col1.metric("Saída Máx", f"{df['out_display'].max():.2f} {unit}")
        col2.metric("Saída Mín", f"{df['out_display'].min():.2f} {unit}")
        col3.metric("Última Saída", f"{df['out_display'].iloc[-1]:.2f} {unit}")

    # Download do gráfico como PNG
    img_bytes = fig.to_image(format="png")
    st.download_button(
        label="📷 Baixar Gráfico como PNG",
        data=img_bytes,
        file_name="trafego.png",
        mime="image/png"
    )


# ---------- Estado Inicial ----------
for key in ["interfaces", "session", "monitoring", "traffic_data", "prev_in", "prev_out", "first_collection_skipped", "prev_time"]:
    if key not in st.session_state:
        if key in ["session", "prev_time"]:
            st.session_state[key] = None
        elif key == "traffic_data":
            st.session_state[key] = []
        elif key == "monitoring":
            st.session_state[key] = False
        else:
            st.session_state[key] = 0 if "prev_" in key else {}

# ---------- Página ----------
st.set_page_config(page_title="Monitoramento SNMP", page_icon="📡", layout="wide")
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stDeployButton {display: none;}
    .st-emotion-cache-fblp2m {display: none;}
    </style>
""", unsafe_allow_html=True)

st.title("Monitoramento SNMP (Modo Precisão)")
ip = st.text_input("IP do equipamento")
community = st.text_input("Community SNMP", value="public")
version_str = st.selectbox("Versão SNMP", ["2c", "1"])
version = 2 if version_str == "2c" else 1

col1, col2 = st.columns(2)
with col1:
    if st.button("Listar interfaces"):
        if not is_valid_ip(ip):
            st.warning("IP inválido.")
        else:
            with st.spinner("Listando interfaces..."):
                try:
                    session = get_snmp_session(ip, community, version)
                    interfaces = get_interfaces(session)
                    if not interfaces:
                        st.warning("Nenhuma interface encontrada.")
                    else:
                        st.session_state.session = session
                        st.session_state.interfaces = interfaces
                except Exception as e:
                    st.error(f"Erro: {e}")
with col2:
    if st.button("Limpar"):
        st.session_state.interfaces = {}
        st.session_state.session = None
        st.session_state.monitoring = False
        st.session_state.traffic_data = []
        st.success("Resetado.")

if st.session_state.interfaces:
    selected_name = st.selectbox("Interface", list(st.session_state.interfaces.values()))
    selected_index = next(k for k, v in st.session_state.interfaces.items() if v == selected_name)

    col3, col4 = st.columns([1, 1])
    monitor_in = col3.checkbox("Monitorar entrada", value=True)
    monitor_out = col4.checkbox("Monitorar saída", value=True)

    col5, col6 = st.columns([1, 1])
    with col5:
        if st.button("Iniciar"):
            st.session_state.monitoring = True
            st.session_state.traffic_data = []
            st.session_state.first_collection_skipped = False
            st.success("Monitoramento iniciado!")

    with col6:
        if st.button("Parar"):
            st.session_state.monitoring = False
            st.success("Monitoramento parado.")

    chart_container = st.empty()
    num_points = st.slider("Pontos no gráfico", 5, 300, 60, step=5)

    if st.session_state.monitoring:
        try:
            oct_in, oct_out = get_traffic_in_out(st.session_state.session, selected_index)
            current_time = datetime.now()

            # Ignora a primeira coleta
            if not st.session_state.first_collection_skipped:
                st.session_state.prev_in = oct_in
                st.session_state.prev_out = oct_out
                st.session_state.prev_time = current_time
                st.session_state.first_collection_skipped = True
                time.sleep(1)
                st.rerun()

            prev_in = st.session_state.prev_in
            prev_out = st.session_state.prev_out
            prev_time = st.session_state.prev_time

            st.session_state.prev_in = oct_in
            st.session_state.prev_out = oct_out
            st.session_state.prev_time = current_time

            time_diff = (current_time - prev_time).total_seconds()
            diff_in = oct_in - prev_in
            diff_out = oct_out - prev_out

            if time_diff < 0.5 or time_diff > 3:
                st.warning(f"Δtempo fora do intervalo ({time_diff:.2f}s). Ignorado.")
                time.sleep(1)
                st.rerun()

            if diff_in < 0 or diff_out < 0:
                st.warning("Delta SNMP negativo. Ignorando coleta.")
                time.sleep(1)
                st.rerun()

            if diff_in == 0 and diff_out == 0:
                st.warning("Coleta sem variação. Ignorada.")
                time.sleep(1)
                st.rerun()

            mbps_in = (diff_in * 8) / (time_diff * 1_000_000)
            mbps_out = (diff_out * 8) / (time_diff * 1_000_000)

            st.session_state.traffic_data.append({
                "timestamp": current_time.strftime("%H:%M:%S"),
                "in": round(mbps_in, 2),
                "out": round(mbps_out, 2),
                "oct_in": oct_in,
                "oct_out": oct_out,
                "delta_time": round(time_diff, 3)
            })

            df = pd.DataFrame(st.session_state.traffic_data)[-num_points:]
            plot_graph(df, monitor_in, monitor_out, chart_container)

            time.sleep(1)
            st.rerun()

        except Exception as e:
            st.error(f"Erro durante o monitoramento: {e}")
            st.session_state.monitoring = False

    if not st.session_state.monitoring and st.session_state.traffic_data:
        df = pd.DataFrame(st.session_state.traffic_data)[-num_points:]
        plot_graph(df, monitor_in, monitor_out, chart_container)

    if st.session_state.traffic_data:
        df = pd.DataFrame(st.session_state.traffic_data)
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Baixar CSV", csv, file_name=f"{selected_name}_trafego.csv", mime="text/csv")
