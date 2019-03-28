FROM continuumio/miniconda3:4.5.12 as builder

WORKDIR /build

COPY . .

RUN conda install -c conda-forge -y conda-build && \
      conda build -c conda-forge .

FROM continuumio/miniconda3:4.5.12

COPY --from=builder /opt/conda/conda-bld/noarch/* /opt/conda/conda-bld/noarch/

RUN conda install -c conda-forge --use-local nimbus-k8s-provisioner

EXPOSE 8000

ENTRYPOINT ["nimbus-provisioner"]
